#!/usr/bin/env python3
"""
Skeleton lint: enforce line-count thresholds on CLAUDE.md files.

Prevents config creep by failing when CLAUDE.md files grow beyond
their budgeted size. Run as part of daily maintenance or CI.

Usage:
    python skeleton_lint.py [--project-cap 150] [--user-cap 80] [path ...]

If no paths given, checks common locations:
  - ./CLAUDE.md (project)
  - ~/.claude/CLAUDE.md (user)
"""

import argparse
import os
import sys
from pathlib import Path


DEFAULT_PROJECT_CAP = 150
DEFAULT_USER_CAP = 80


def lint_file(path: str, cap: int) -> tuple[bool, int]:
    """Check a file against a line-count cap.

    Returns: (passed, line_count)
    """
    p = Path(path)
    if not p.exists():
        return True, 0  # Missing file is fine (not our problem)

    line_count = len(p.read_text().splitlines())
    return line_count <= cap, line_count


def main():
    parser = argparse.ArgumentParser(
        description="Enforce line-count caps on CLAUDE.md files",
    )
    parser.add_argument("paths", nargs="*", help="Files to check")
    parser.add_argument("--project-cap", type=int, default=DEFAULT_PROJECT_CAP,
                        help=f"Max lines for project CLAUDE.md (default: {DEFAULT_PROJECT_CAP})")
    parser.add_argument("--user-cap", type=int, default=DEFAULT_USER_CAP,
                        help=f"Max lines for user CLAUDE.md (default: {DEFAULT_USER_CAP})")
    args = parser.parse_args()

    if args.paths:
        targets = [(p, args.project_cap) for p in args.paths]
    else:
        targets = [
            ("./CLAUDE.md", args.project_cap),
            (os.path.expanduser("~/.claude/CLAUDE.md"), args.user_cap),
        ]

    failed = False
    for path, cap in targets:
        passed, count = lint_file(path, cap)
        status = "OK" if passed else "OVER"
        print(f"  {status}  {count:>4}/{cap}  {path}")
        if not passed:
            failed = True

    if failed:
        print("\nSkeleton lint FAILED. Reduce line counts or extract detail to packs.")
        sys.exit(1)
    else:
        print("\nSkeleton lint passed.")


if __name__ == "__main__":
    main()
