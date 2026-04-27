#!/usr/bin/env python3
"""
Breakout session manager.

Manages git worktrees for isolated worker sessions. A "breakout"
is a long-running worker that gets its own worktree, branch, and
context-isolated environment.

Usage:
    python breakout.py launch <slug> [--executor opus] [--task-file brief.md]
    python breakout.py launch <slug> --interactive
    python breakout.py status <worker-id>
    python breakout.py done <worker-id>
    python breakout.py lint <brief-path>
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dispatch_lib.path_conventions import dispatch_root, ensure_dirs, log_path, status_path
from dispatch_lib.status_writer import init_status, read_status, finalize


WORKTREE_BASE = ".claude/worktrees"


def cmd_launch(args):
    """Launch a breakout session in its own git worktree."""
    slug = args.slug
    cwd = args.cwd or os.getcwd()
    executor = args.executor or "sonnet"
    task_file = args.task_file

    # Validate we're in a git repo
    git_root = _find_git_root(cwd)
    if not git_root:
        print("Error: Not in a git repo. Breakout requires git for worktree isolation.", file=sys.stderr)
        sys.exit(1)

    # Create branch and worktree
    branch = f"worktree-{slug}"
    worktree_dir = os.path.join(git_root, WORKTREE_BASE, slug)

    if os.path.exists(worktree_dir):
        print(f"Worktree already exists: {worktree_dir}")
        print("Use a different slug or remove the existing worktree.")
        sys.exit(1)

    # Create worktree from current HEAD
    os.makedirs(os.path.dirname(worktree_dir), exist_ok=True)
    result = subprocess.run(
        ["git", "-C", git_root, "worktree", "add", worktree_dir, "-b", branch],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        # Branch might exist already; try without -b
        result = subprocess.run(
            ["git", "-C", git_root, "worktree", "add", worktree_dir, branch],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"Error creating worktree: {result.stderr}", file=sys.stderr)
            sys.exit(1)

    print(f"Created worktree: {worktree_dir} (branch: {branch})")

    # If interactive mode, just print the path
    if args.interactive:
        print(f"Interactive mode. cd to: {worktree_dir}")
        print(f"When done: python breakout.py done <worker-id>")
        return

    # Non-interactive: dispatch via CLI
    dispatch_cmd = [
        sys.executable, str(Path(__file__).parent / "cli.py"),
        "breakout", "start",
        "--executor", executor,
        "--cwd", worktree_dir,
        "--slug", slug,
    ]
    if task_file:
        dispatch_cmd.extend(["--task-file", str(Path(task_file).resolve())])

    # Pass through nested dispatch args
    if args.parent_id:
        dispatch_cmd.extend(["--parent-id", args.parent_id])
    if args.parent_executor:
        dispatch_cmd.extend(["--parent-executor", args.parent_executor])
    if args.depth:
        dispatch_cmd.extend(["--depth", str(args.depth)])
    if args.budget_remaining is not None:
        dispatch_cmd.extend(["--budget-remaining", str(args.budget_remaining)])
    if args.deadline:
        dispatch_cmd.extend(["--deadline", args.deadline])

    # Inject nested dispatch env if brief declares it
    env = os.environ.copy()
    if task_file and _brief_declares_nested(task_file):
        env["DISPATCH_NESTED"] = "1"
        max_depth = _brief_nested_max_depth(task_file)
        if max_depth:
            env["DISPATCH_MAX_DEPTH"] = str(max_depth)

    result = subprocess.run(dispatch_cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Dispatch failed: {result.stderr}", file=sys.stderr)
        sys.exit(result.returncode)

    worker_id = result.stdout.strip()
    print(f"Dispatched: {worker_id}")
    print(f"Worktree: {worktree_dir}")
    print(f"Branch: {branch}")


def cmd_status(args):
    """Show status for a breakout worker."""
    status = read_status(args.worker_id)
    if not status:
        print(f"Worker not found: {args.worker_id}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(status, indent=2))


def cmd_done(args):
    """Mark a breakout session as done and clean up."""
    status = read_status(args.worker_id)
    if not status:
        print(f"Worker not found: {args.worker_id}", file=sys.stderr)
        sys.exit(1)

    finalize(args.worker_id, "done", exit_code=0)
    print(f"Finalized: {args.worker_id}")

    # Note: worktree cleanup is manual (user may want to review changes)
    print("Worktree preserved for review. Remove manually with:")
    print(f"  git worktree remove <path>")


def cmd_lint(args):
    """Lint a brief file for common issues."""
    brief_path = args.brief_path
    if not os.path.exists(brief_path):
        print(f"Brief not found: {brief_path}", file=sys.stderr)
        sys.exit(1)

    content = Path(brief_path).read_text()
    errors = []
    warnings = []

    # Check for includes references
    for line in content.splitlines():
        if line.startswith("includes:"):
            # Validate pack names exist
            pass  # Pack validation happens at assembly time

    # Check for relative paths (should be absolute in briefs)
    rel_path_pattern = re.compile(r'(?:^|\s)(\.\.?/[^\s]+)', re.MULTILINE)
    for match in rel_path_pattern.finditer(content):
        warnings.append(f"Relative path detected: {match.group(1)} (use absolute paths in briefs)")

    # Check for task/context sections
    if "## Task" not in content and "task:" not in content.lower()[:200]:
        warnings.append("Brief has no ## Task section or task: field")

    if errors:
        print("Errors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    if warnings:
        print("Warnings:")
        for w in warnings:
            print(f"  - {w}")
    else:
        print("Brief looks good.")


# --- Helpers ---

def _find_git_root(path: str) -> str | None:
    """Find the git root directory."""
    result = subprocess.run(
        ["git", "-C", path, "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return None


def _brief_declares_nested(task_file: str) -> bool:
    """Check if a brief declares nested dispatch capability."""
    try:
        content = Path(task_file).read_text()
        return "nested_dispatch:" in content
    except (OSError, UnicodeDecodeError):
        return False


def _brief_nested_max_depth(task_file: str) -> int | None:
    """Extract max_depth from brief's nested_dispatch block."""
    try:
        content = Path(task_file).read_text()
        match = re.search(r'max_depth:\s*(\d+)', content)
        if match:
            return int(match.group(1))
    except (OSError, UnicodeDecodeError):
        pass
    return None


def main():
    parser = argparse.ArgumentParser(
        prog="breakout",
        description="Breakout session manager for worktree-isolated dispatch",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # launch
    launch_parser = subparsers.add_parser("launch", help="Launch a breakout session")
    launch_parser.add_argument("slug", help="Short name for the worktree")
    launch_parser.add_argument("--executor", default="sonnet", help="Executor name")
    launch_parser.add_argument("--task-file", help="Path to brief file")
    launch_parser.add_argument("--cwd", help="Project directory")
    launch_parser.add_argument("--interactive", action="store_true", help="Interactive mode (no auto-dispatch)")
    launch_parser.add_argument("--parent-id", dest="parent_id", help="Parent worker ID")
    launch_parser.add_argument("--parent-executor", dest="parent_executor", help="Parent executor")
    launch_parser.add_argument("--depth", type=int, default=0, help="Nesting depth")
    launch_parser.add_argument("--budget-remaining", dest="budget_remaining", type=float)
    launch_parser.add_argument("--deadline", help="ISO-8601 deadline")

    # status
    status_parser = subparsers.add_parser("status", help="Show breakout status")
    status_parser.add_argument("worker_id", help="Worker ID")

    # done
    done_parser = subparsers.add_parser("done", help="Mark breakout as done")
    done_parser.add_argument("worker_id", help="Worker ID")

    # lint
    lint_parser = subparsers.add_parser("lint", help="Lint a brief file")
    lint_parser.add_argument("brief_path", help="Path to brief file")

    args = parser.parse_args()

    if args.command == "launch":
        cmd_launch(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "done":
        cmd_done(args)
    elif args.command == "lint":
        cmd_lint(args)


if __name__ == "__main__":
    main()
