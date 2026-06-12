#!/usr/bin/env python3
"""
pushing-dispatch CLI - Multi-model dispatch for AI coding agents.

Usage:
    python cli.py task start --executor sonnet --task-file brief.md --cwd /path/to/project
    python cli.py breakout start --executor opus --task-file brief.md --cwd /path/to/project
    python cli.py list [--tree] [--active]
    python cli.py status <worker-id>
    python cli.py kill <worker-id> [--no-cascade]
    python cli.py budget [--tree]
    python cli.py completions
    python cli.py questions
    python cli.py answer <worker-id> --answer-file <path>
    python cli.py compact
    python cli.py validate-matrix <matrix-path>
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

# Add parent dir so dispatch_lib is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dispatch_lib.path_conventions import (
    dispatch_root, status_dir, log_dir, registry_path,
    status_path, log_path, question_dir, question_path, ensure_dirs,
)
from dispatch_lib.status_writer import (
    init_status, set_phase, finalize, read_status, is_terminal, PHASES,
)
from dispatch_lib.budget import record_spend, today_total, tree_breakdown_today
from dispatch_lib.feature_flag import (
    is_nested_dispatch_enabled, get_depth_cap,
)
from dispatch_lib.permissions import check_nested_permission
from dispatch_lib.nested import (
    build_tree, children_of, tree_for, kill_cascade, format_tree,
)
from dispatch_lib.matrix_validator import validate
from dispatch_lib.context_budget import check_budget_for_file
from dispatch_lib.auto_router import (
    auto_route, detect_mode_from_keywords, _tier, _candidates,
)
from dispatch_lib import availability, lane_health

try:
    import tomllib
except ImportError:  # pragma: no cover
    tomllib = None

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


# --- Executor loading from matrix ---

def _find_matrix_path() -> str | None:
    """Find dispatch_matrix.toml by searching common locations."""
    candidates = [
        os.environ.get("DISPATCH_MATRIX", ""),
        str(Path(__file__).parent / "dispatch_matrix.toml"),
        str(dispatch_root() / "dispatch_matrix.toml"),
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def _load_matrix() -> dict:
    """Load the dispatch matrix TOML."""
    path = _find_matrix_path()
    if not path or not tomllib:
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def _executor_choices(matrix: dict) -> list[str]:
    """Derive executor names from the matrix."""
    return list(matrix.get("executors", {}).keys())


def _build_executors(matrix: dict) -> dict:
    """Build executor -> wrapper mapping from matrix."""
    result = {}
    for name, config in matrix.get("executors", {}).items():
        result[name] = config.get("wrapper", f"{name}.sh")
    return result


# --- Worker ID generation ---

def _generate_worker_id(slug: str) -> str:
    """Generate a unique worker ID: w-<hex4>-<slug>"""
    import hashlib
    h = hashlib.sha256(f"{time.time()}-{slug}".encode()).hexdigest()[:4]
    safe_slug = slug[:40].replace(" ", "-").lower()
    return f"w-{h}-{safe_slug}"


# --- Registry ---

def _append_registry(entry: dict):
    """Append an entry to the session registry."""
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _read_registry() -> list[dict]:
    """Read all registry entries."""
    path = registry_path()
    if not path.exists():
        return []
    entries = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


# --- Nested dispatch gates ---

def _check_nested_dispatch_gates(args, matrix_path: str) -> tuple[bool, str, int]:
    """Check all nested dispatch safety gates.

    Returns: (passed, reason, exit_code)
    Exit codes: 0=ok, 3=budget, 4=depth, 5=permission, 6=deadline
    """
    parent_id = getattr(args, "parent_id", None)
    depth = getattr(args, "depth", 0)

    if not parent_id:
        return True, "", 0

    if not is_nested_dispatch_enabled():
        # Silently ignore nesting flags when feature is off
        return True, "", 0

    # Depth check
    depth_cap = get_depth_cap()
    if depth >= depth_cap:
        return False, f"DEPTH_EXCEEDED: depth={depth}, max={depth_cap}", 4

    # Permission check
    parent_executor = getattr(args, "parent_executor", None)
    executor = args.executor
    if parent_executor:
        allowed, reason = check_nested_permission(parent_executor, executor, matrix_path)
        if not allowed:
            return False, f"PERMISSION_DENIED: {reason}", 5

    # Budget check
    budget_remaining = getattr(args, "budget_remaining", None)
    if budget_remaining is not None and budget_remaining <= 0:
        return False, f"BUDGET_EXHAUSTED: remaining={budget_remaining}", 3

    # Deadline check
    deadline_str = getattr(args, "deadline", None)
    if deadline_str:
        try:
            deadline = datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
            now = datetime.now(deadline.tzinfo)
            if now >= deadline:
                return False, f"DEADLINE_EXCEEDED: deadline={deadline_str}", 6
        except (ValueError, TypeError):
            pass

    return True, "", 0


# --- Subcommands ---

def cmd_start(args, mode: str):
    """Start a new worker (task or breakout)."""
    ensure_dirs()
    matrix = _load_matrix()
    matrix_path = _find_matrix_path()

    tier = "explicit"
    if getattr(args, "executor", "auto") in ("", None, "auto"):
        brief_text = _brief_text_from_args(args)
        args.executor, tier = auto_route(
            brief_text=brief_text,
            mode=mode,
            matrix_path=matrix_path,
            explicit_executor=None,
            return_tier=True,
        )

    # Validate executor
    valid_executors = _executor_choices(matrix) if matrix else []
    if valid_executors and args.executor not in valid_executors:
        print(f"Error: Unknown executor '{args.executor}'. Valid: {valid_executors}", file=sys.stderr)
        sys.exit(1)

    # Check nested dispatch gates
    passed, reason, exit_code = _check_nested_dispatch_gates(args, matrix_path)
    if not passed:
        print(f"Error: {reason}", file=sys.stderr)
        sys.exit(exit_code)

    # Generate worker ID
    slug = getattr(args, "slug", None) or Path(args.task_file).stem if args.task_file else mode
    worker_id = _generate_worker_id(slug)

    # Resolve wrapper
    executors_map = _build_executors(matrix) if matrix else {}
    wrapper = executors_map.get(args.executor, f"{args.executor}.sh")
    wrapper_path = Path(__file__).parent / "bin" / "wrappers" / wrapper

    if not wrapper_path.exists():
        print(f"Error: Wrapper not found: {wrapper_path}", file=sys.stderr)
        sys.exit(1)

    # Build wrapper command
    cmd = [
        str(wrapper_path),
        "--worker-id", worker_id,
        "--cwd", args.cwd or os.getcwd(),
        "--mode", mode,
    ]

    if args.task_file:
        cmd.extend(["--task-file", str(Path(args.task_file).resolve())])
    if args.task:
        cmd.extend(["--task", args.task])

    # Pass executor identity + tier so the wrapper can attribute self-healing
    # cooldowns and outcomes to the correct matrix executor (not just the tool).
    env = os.environ.copy()
    env["CE_EXECUTOR_NAME"] = args.executor
    env["CE_TIER"] = tier
    _exec_cfg = (matrix.get("executors", {}) if matrix else {}).get(args.executor, {})
    if _exec_cfg.get("account"):
        env["CE_OPENAI_ACCOUNT"] = _exec_cfg["account"]

    # Pass nested dispatch env vars
    parent_id = getattr(args, "parent_id", None)
    depth = getattr(args, "depth", 0)

    if parent_id and is_nested_dispatch_enabled():
        env["DISPATCH_NESTED"] = "1"
        env["DISPATCH_CURRENT_DEPTH"] = str(depth)
        env["DISPATCH_WORKER_ID"] = worker_id
        if getattr(args, "budget_remaining", None) is not None:
            env["DISPATCH_BUDGET_REMAINING"] = str(args.budget_remaining)
        if getattr(args, "deadline", None):
            env["DISPATCH_DEADLINE"] = args.deadline
    else:
        env["DISPATCH_WORKER_ID"] = worker_id

    # Initialize status
    proc = subprocess.Popen(
        cmd,
        env=env,
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    init_status(
        worker_id=worker_id,
        mode=mode,
        executor=args.executor,
        pid=proc.pid,
        brief_path=args.task_file or "",
        log_file=str(log_path(worker_id)),
        parent_id=parent_id,
        depth=depth,
        session_id=os.environ.get("DISPATCH_SESSION_ID"),
    )

    # Registry entry
    _append_registry({
        "kind": "bg-event",
        "event": "worker_started",
        "worker_id": worker_id,
        "mode": mode,
        "executor": args.executor,
        "pid": proc.pid,
        "parent_id": parent_id,
        "depth": depth,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })

    print(worker_id)


def cmd_list(args):
    """List workers."""
    ensure_dirs()
    entries = _load_all_statuses()

    if args.active:
        entries = [e for e in entries if not is_terminal(e.get("current_phase", "done"))]

    if not entries:
        print("No workers found.")
        return

    if args.tree:
        print(format_tree(entries))
    else:
        for e in entries:
            wid = e["worker_id"]
            executor = e.get("executor", "?")
            mode = e.get("mode", "?")
            phase = e.get("current_phase", "?")
            started = e.get("started_at", "?")
            depth = e.get("depth", 0)
            depth_str = f" (depth {depth})" if depth > 0 else ""
            print(f"{wid}  {executor:>10}  {mode:>8}  {phase:>16}  {started}{depth_str}")


def cmd_status(args):
    """Show status for a specific worker."""
    status = read_status(args.worker_id)
    if not status:
        print(f"Worker not found: {args.worker_id}", file=sys.stderr)
        sys.exit(1)

    if args.field:
        print(status.get(args.field, ""))
    else:
        print(json.dumps(status, indent=2))


def cmd_kill(args):
    """Kill a worker (and optionally its children)."""
    entries = _load_all_statuses()
    target = next((e for e in entries if e["worker_id"] == args.worker_id), None)

    if not target:
        print(f"Worker not found: {args.worker_id}", file=sys.stderr)
        sys.exit(1)

    if args.no_cascade:
        pid = target.get("pid")
        if pid:
            try:
                os.kill(pid, 15)
            except (ProcessLookupError, PermissionError):
                pass
        finalize(args.worker_id, "killed", exit_code=-15, error_summary="Killed by operator")
        print(f"Killed: {args.worker_id}")
    else:
        killed = kill_cascade(args.worker_id, entries)
        for wid in killed:
            print(f"Killed: {wid}")


def cmd_budget(args):
    """Show budget information."""
    if args.tree:
        trees = tree_breakdown_today()
        if not trees:
            print("No spend recorded today.")
            return
        for root, data in trees.items():
            print(f"  {root}")
            for w in data["workers"]:
                cost = w.get("cost", 0.0)
                currency = w.get("currency", "USD")
                print(f"    {w['worker_id']}  {currency} {cost:.4f}")
            print(f"  Tree total: {data['total']:.4f}")
            print()
    else:
        total = today_total()
        print(f"Today's total: USD {total:.4f}")


def cmd_completions(args):
    """List recently completed workers (for polling)."""
    entries = _load_all_statuses()
    completed = [
        e for e in entries
        if is_terminal(e.get("current_phase", ""))
        and e.get("finalized_at")
    ]

    # Sort by finalized_at, most recent first
    completed.sort(key=lambda e: e.get("finalized_at", ""), reverse=True)

    # Show last 10
    for e in completed[:10]:
        wid = e["worker_id"]
        phase = e.get("current_phase", "?")
        when = e.get("finalized_at", "?")
        print(f"{wid}  {phase}  {when}")


def cmd_questions(args):
    """List pending question files."""
    qdir = question_dir()
    if not qdir.exists():
        return

    for qfile in sorted(qdir.glob("*.md")):
        print(f"  {qfile.stem}")
        # Show first few lines
        lines = qfile.read_text().splitlines()[:5]
        for line in lines:
            print(f"    {line}")
        print()


def cmd_validate_matrix(args):
    """Validate a dispatch matrix TOML file."""
    errors = validate(args.matrix_path)
    if errors:
        print("Validation errors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("Matrix is valid.")


def _brief_text_from_args(args) -> str:
    if getattr(args, "task_file", None):
        return Path(args.task_file).read_text()
    if getattr(args, "task", None):
        return args.task
    return ""


def cmd_route(args):
    """Select the best executor for a task without starting it."""
    matrix_path = args.matrix or _find_matrix_path()
    brief_text = _brief_text_from_args(args)
    mode = args.mode or detect_mode_from_keywords(brief_text) or "task"
    executor, tier = auto_route(
        brief_text=brief_text,
        mode=mode,
        matrix_path=matrix_path,
        explicit_executor=args.executor,
        return_tier=True,
    )
    if args.json:
        payload = {
            "executor": executor,
            "mode": mode,
            "tier": tier,
            "matrix": matrix_path,
            "estimated_tokens": len(brief_text) // 4,
        }
        # Enrich with availability + which earlier candidates were skipped.
        if matrix_path and tomllib and os.path.exists(matrix_path):
            with open(matrix_path, "rb") as f:
                matrix = tomllib.load(f)
            avail = availability.available_set(matrix)
            route_cfg = matrix.get("auto_route", {})
            list_key, legacy = _tier(brief_text, mode, route_cfg)
            considered = _candidates(route_cfg, list_key, legacy)
            fallback_from = []
            for cand in considered:
                if cand == executor:
                    break
                if cand not in avail or lane_health.in_cooldown(cand):
                    fallback_from.append(cand)
            payload["considered"] = considered
            payload["fallback_from"] = fallback_from
            payload["available"] = sorted(avail)
        print(json.dumps(payload, indent=2))
    else:
        print(executor)


def _doctor_rows(matrix):
    """Build a live availability/health row per executor."""
    avail = availability.resolve(matrix, use_cache=False)
    relogin = set(lane_health.needs_relogin())
    rows = []
    for name, cfg in matrix.get("executors", {}).items():
        a = avail.get(name, {"available": False, "provider": cfg.get("provider", "")})
        rows.append({
            "executor": name,
            "provider": a["provider"],
            "available": a["available"],
            "cooldown": lane_health.in_cooldown(name),
            "needs_relogin": name in relogin,
        })
    return rows


def _probe_executor(name, cfg, repo_root):
    """Live end-to-end probe through the lane's real wrapper.

    Availability checks are presence-only (key/file exists), which let five
    broken lanes report "available" on 2026-06-12. A probe dispatches one
    tiny request through the production wrapper path — catching stale keys,
    env contamination, permission-mode failures, and no-op integrations.
    Costs ~1 minimal model call per lane.
    """
    import tempfile

    wrapper = cfg.get("wrapper")
    if not wrapper:
        return {"executor": name, "probe": "SKIP", "detail": "no wrapper"}
    wrapper_path = os.path.join(repo_root, "bin", "wrappers", wrapper)
    if not os.path.exists(wrapper_path):
        return {"executor": name, "probe": "SKIP", "detail": "wrapper missing"}
    modes = cfg.get("allowed_modes", [])
    mode = "task" if "task" in modes else ("consult" if "consult" in modes else None)
    if mode is None:
        return {"executor": name, "probe": "SKIP", "detail": f"no probeable mode in {modes}"}

    probe_root = tempfile.mkdtemp(prefix="dispatch-probe-")
    worker_id = f"probe-{name}-{int(time.time())}"
    env = os.environ.copy()
    env["DISPATCH_ROOT"] = probe_root  # keep probe status/logs out of the registry
    cmd = [
        wrapper_path,
        "--task", "Reply with exactly: OK",
        "--worker-id", worker_id,
        "--mode", mode,
        "--max-turns", "1",
        "--cwd", probe_root,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)
    except subprocess.TimeoutExpired:
        return {"executor": name, "probe": "TIMEOUT", "detail": "no response in 120s"}

    out = (proc.stdout or "") + (proc.stderr or "")
    log_path = os.path.join(probe_root, "logs", f"{worker_id}.log")
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", errors="replace") as f:
                out += f.read()[-4000:]
        except OSError:
            pass

    if proc.returncode == 0:
        return {"executor": name, "probe": "OK", "detail": ""}
    lowered = out.lower()
    auth_markers = ("401", "invalid bearer", "invalid api key", "invalid authentication",
                    "refresh token", "unauthorized")
    if any(m in lowered for m in auth_markers):
        return {"executor": name, "probe": "AUTH_FAIL", "detail": f"rc={proc.returncode}"}
    return {"executor": name, "probe": "ERROR", "detail": f"rc={proc.returncode}"}


def cmd_doctor(args):
    """Print live executor availability and lane health."""
    matrix_path = args.matrix or _find_matrix_path()
    if not (matrix_path and tomllib and os.path.exists(matrix_path)):
        print("No matrix found.", file=sys.stderr)
        return
    with open(matrix_path, "rb") as f:
        matrix = tomllib.load(f)
    rows = _doctor_rows(matrix)

    probe_results = {}
    probe_arg = getattr(args, "probe", None)
    if probe_arg is not None:
        executors = matrix.get("executors", {})
        if probe_arg:
            targets = [n for n in probe_arg if n in executors]
            for n in probe_arg:
                if n not in executors:
                    print(f"probe: unknown executor '{n}'", file=sys.stderr)
        else:
            # Default sweep skips openai-codex lanes: probing them consumes the
            # account's single-use OAuth refresh token and can race interactive
            # sessions (the 2026-06-12 auth.json lockout). Name them explicitly
            # to probe anyway.
            targets = [
                r["executor"] for r in rows
                if r["available"] and executors.get(r["executor"], {}).get("provider") != "openai-codex"
            ]
        repo_root = os.path.dirname(os.path.abspath(matrix_path))
        for n in targets:
            probe_results[n] = _probe_executor(n, executors[n], repo_root)

    for r in rows:
        if r["executor"] in probe_results:
            p = probe_results[r["executor"]]
            r["probe"] = p["probe"]
            r["probe_detail"] = p["detail"]

    if getattr(args, "json", False):
        print(json.dumps(rows, indent=2))
        return
    header = f"{'EXECUTOR':24} {'PROVIDER':22} {'STATE':14}"
    if probe_results:
        header += " PROBE"
    print(header)
    print("-" * (64 if not probe_results else 80))
    for r in sorted(rows, key=lambda x: (not x["available"], x["executor"])):
        state = "available" if r["available"] else "UNAVAILABLE"
        if r["cooldown"]:
            state = "cooldown"
        if r["needs_relogin"]:
            state = "NEEDS RE-LOGIN"
        line = f"{r['executor']:24} {r['provider']:22} {state:14}"
        if probe_results:
            p = r.get("probe", "")
            d = r.get("probe_detail", "")
            line += f" {p}{(' (' + d + ')') if d else ''}"
        print(line)


def cmd_answer(args):
    """Re-dispatch a worker with the operator's answer baked into the brief."""
    ensure_dirs()
    status = read_status(args.worker_id)
    if not status:
        print(f"Error: no worker '{args.worker_id}'", file=sys.stderr)
        sys.exit(2)

    if args.answer_file:
        answer_text = Path(args.answer_file).read_text()
    elif args.answer:
        answer_text = args.answer
    else:
        print("Error: --answer or --answer-file required", file=sys.stderr)
        sys.exit(2)

    orig_task_file = Path(status.get("brief_path", ""))
    if not orig_task_file.exists():
        print(f"Error: original task file missing: {orig_task_file}", file=sys.stderr)
        sys.exit(2)

    orig_task = orig_task_file.read_text()

    # Build the revised task with the answer appended.
    import re as _re
    base_label = status.get("worker_id", "re")
    rev_match = _re.match(r"^(.*)-r(\d+)$", base_label)
    if rev_match:
        new_label = f"{rev_match.group(1)}-r{int(rev_match.group(2)) + 1}"
    else:
        new_label = f"{base_label}-r1"

    new_task = (
        orig_task.rstrip()
        + "\n\n## Operator answer to your question\n\n"
        + answer_text.rstrip()
        + "\n"
    )
    task_archive = dispatch_root() / "tasks"
    task_archive.mkdir(parents=True, exist_ok=True)
    import uuid as _uuid
    new_task_file = task_archive / f"{new_label}-{_uuid.uuid4().hex[:4]}.task.md"
    new_task_file.write_text(new_task)

    # Archive the old question file if present.
    qpath = question_path(args.worker_id)
    if qpath.exists():
        resolved = question_dir() / "_resolved"
        resolved.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        dest = resolved / f"{args.worker_id}-{ts}.md"
        qpath.rename(dest)

    # Registry entry for resolution.
    _append_registry({
        "kind": "bg-event",
        "event": "resolved",
        "worker_id": args.worker_id,
        "status": "resolved",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })

    # Re-dispatch with same executor.
    executor = status.get("executor", "sonnet")
    cwd = status.get("cwd") or os.getcwd()
    matrix = _load_matrix()
    executors_map = _build_executors(matrix) if matrix else {}
    wrapper = executors_map.get(executor, f"{executor}.sh")
    wrapper_path = Path(__file__).parent / "bin" / "wrappers" / wrapper

    worker_id = _generate_worker_id(new_label)
    cmd = [
        str(wrapper_path),
        "--worker-id", worker_id,
        "--cwd", cwd,
        "--mode", status.get("mode", "task"),
        "--task-file", str(new_task_file),
    ]

    env = os.environ.copy()
    env["DISPATCH_WORKER_ID"] = worker_id

    proc = subprocess.Popen(
        cmd, env=env, start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    init_status(
        worker_id=worker_id,
        mode=status.get("mode", "task"),
        executor=executor,
        pid=proc.pid,
        brief_path=str(new_task_file),
        log_file=str(log_path(worker_id)),
        parent_id=args.worker_id,
        depth=status.get("depth", 0),
        session_id=os.environ.get("DISPATCH_SESSION_ID"),
    )

    _append_registry({
        "kind": "bg-event",
        "event": "worker_started",
        "worker_id": worker_id,
        "mode": status.get("mode", "task"),
        "executor": executor,
        "pid": proc.pid,
        "parent_id": args.worker_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })

    print(worker_id)


def cmd_checkpoint(args):
    """Checkpoint subcommand dispatcher."""
    if args.checkpoint_command == "list":
        cmd_checkpoint_list(args)
    elif args.checkpoint_command == "continue":
        cmd_checkpoint_continue(args)


def cmd_checkpoint_list(args):
    """List awaiting checkpoints."""
    from dispatch_lib import checkpoint as _ck
    items = _ck.list_awaiting_checkpoints()
    if args.json:
        payload = [
            {
                "worker_id": c.worker_id,
                "slug": c.slug,
                "phase": c.phase,
                "commit_sha": c.commit_sha,
                "timestamp": c.timestamp,
                "path": str(c.path),
            }
            for c in items
        ]
        print(json.dumps(payload, indent=2))
        return
    if not items:
        print("(no awaiting checkpoints)")
        return
    print(f"{'WORKER_ID':<24} {'SLUG':<28} {'PHASE':<12} {'COMMIT':<10} TIMESTAMP")
    for c in items:
        print(
            f"{c.worker_id:<24} {c.slug:<28} {c.phase:<12} "
            f"{c.commit_sha[:10]:<10} {c.timestamp}"
        )


def cmd_checkpoint_continue(args):
    """Resume a paused worker by re-dispatching in the same worktree."""
    from dispatch_lib import checkpoint as _ck

    ck = _ck.find_checkpoint_by_worker(args.worker_id)
    if ck is None:
        print(f"Error: no awaiting checkpoint for worker_id {args.worker_id!r}",
              file=sys.stderr)
        sys.exit(2)

    # Default worktree path follows the breakout convention.
    worktree = Path(args.worktree) if args.worktree else None
    if worktree and not worktree.is_dir():
        print(f"Error: worktree not found: {worktree}", file=sys.stderr)
        sys.exit(2)

    # Resolve brief path.
    resume_brief_path = Path(args.task_file).resolve() if args.task_file else None
    if resume_brief_path and not resume_brief_path.exists():
        print(f"Error: brief not found: {resume_brief_path}", file=sys.stderr)
        sys.exit(2)
    if resume_brief_path is None:
        print("Error: --task-file required for checkpoint continue", file=sys.stderr)
        sys.exit(2)

    matrix = _load_matrix()
    executor = args.executor or "sonnet"
    executors_map = _build_executors(matrix) if matrix else {}
    wrapper = executors_map.get(executor, f"{executor}.sh")
    wrapper_path = Path(__file__).parent / "bin" / "wrappers" / wrapper

    _ck.archive_checkpoint(ck)

    new_label = f"{ck.slug}-resume"
    worker_id = _generate_worker_id(new_label)
    cwd = str(worktree) if worktree else os.getcwd()

    cmd = [
        str(wrapper_path),
        "--worker-id", worker_id,
        "--cwd", cwd,
        "--mode", "breakout",
        "--task-file", str(resume_brief_path),
    ]

    env = os.environ.copy()
    env["DISPATCH_WORKER_ID"] = worker_id

    proc = subprocess.Popen(
        cmd, env=env, start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    init_status(
        worker_id=worker_id,
        mode="breakout",
        executor=executor,
        pid=proc.pid,
        brief_path=str(resume_brief_path),
        log_file=str(log_path(worker_id)),
    )

    _append_registry({
        "kind": "bg-event",
        "event": "worker_started",
        "worker_id": worker_id,
        "mode": "breakout",
        "executor": executor,
        "pid": proc.pid,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })

    print(worker_id)


def cmd_compact(args):
    """Compact the session registry (remove old terminal entries)."""
    path = registry_path()
    if not path.exists():
        print("No registry to compact.")
        return

    entries = _read_registry()
    # Keep non-terminal and recent (last 7 days)
    cutoff = (datetime.utcnow().timestamp() - 7 * 86400)
    kept = []
    removed = 0
    for e in entries:
        ts = e.get("timestamp", "")
        try:
            entry_time = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError):
            entry_time = 0
        if entry_time > cutoff:
            kept.append(e)
        else:
            removed += 1

    with open(path, "w") as f:
        for e in kept:
            f.write(json.dumps(e) + "\n")

    print(f"Compacted: removed {removed} entries, kept {len(kept)}")


# --- Helpers ---

def _load_all_statuses() -> list[dict]:
    """Load all status files from the status directory."""
    sdir = status_dir()
    if not sdir.exists():
        return []
    entries = []
    for f in sdir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            entries.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return entries


# --- Main ---

def main():
    matrix = _load_matrix()
    executor_names = _executor_choices(matrix) if matrix else None

    parser = argparse.ArgumentParser(
        prog="pushing-dispatch",
        description="Multi-model dispatch for AI coding agents",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # task start
    task_parser = subparsers.add_parser("task", help="Dispatch a task worker")
    task_sub = task_parser.add_subparsers(dest="task_command", required=True)
    task_start = task_sub.add_parser("start", help="Start a task worker")
    _add_start_args(task_start, executor_names)

    # breakout start
    breakout_parser = subparsers.add_parser("breakout", help="Dispatch a breakout worker")
    breakout_sub = breakout_parser.add_subparsers(dest="breakout_command", required=True)
    breakout_start = breakout_sub.add_parser("start", help="Start a breakout worker")
    _add_start_args(breakout_start, executor_names)

    # list
    list_parser = subparsers.add_parser("list", help="List workers")
    list_parser.add_argument("--tree", action="store_true", help="Tree view")
    list_parser.add_argument("--active", action="store_true", help="Active only")

    # status
    status_parser = subparsers.add_parser("status", help="Show worker status")
    status_parser.add_argument("worker_id", help="Worker ID")
    status_parser.add_argument("--field", help="Show only this field")

    # kill
    kill_parser = subparsers.add_parser("kill", help="Kill a worker")
    kill_parser.add_argument("worker_id", help="Worker ID")
    kill_parser.add_argument("--no-cascade", action="store_true", help="Don't kill children")

    # budget
    budget_parser = subparsers.add_parser("budget", help="Show budget info")
    budget_parser.add_argument("--tree", action="store_true", help="Tree breakdown")

    # completions
    subparsers.add_parser("completions", help="List recent completions")

    # questions
    subparsers.add_parser("questions", help="List pending questions")

    # route
    route_parser = subparsers.add_parser("route", help="Choose the best/cost-efficient executor")
    route_parser.add_argument("--mode", choices=["task", "breakout", "consult"], help="Execution mode")
    route_parser.add_argument("--task-file", help="Path to brief file")
    route_parser.add_argument("--task", help="Inline task string")
    route_parser.add_argument("--executor", default=None, help="Explicit executor override")
    route_parser.add_argument("--matrix", help="Override dispatch matrix path")
    route_parser.add_argument("--json", action="store_true", help="JSON output")

    # answer
    answer_parser = subparsers.add_parser("answer", help="Re-dispatch worker with operator answer baked in")
    answer_parser.add_argument("worker_id", help="Worker ID to answer")
    answer_grp = answer_parser.add_mutually_exclusive_group(required=True)
    answer_grp.add_argument("--answer", help="Inline answer text")
    answer_grp.add_argument("--answer-file", help="Path to answer file")

    # checkpoint
    checkpoint_parser = subparsers.add_parser("checkpoint", help="List or resume advisor-reviewed phased breakouts")
    checkpoint_sub = checkpoint_parser.add_subparsers(dest="checkpoint_command", required=True)

    ck_list = checkpoint_sub.add_parser("list", help="Show workers awaiting advisor review")
    ck_list.add_argument("--json", action="store_true", help="JSON output")

    ck_cont = checkpoint_sub.add_parser("continue", help="Re-dispatch a paused worker")
    ck_cont.add_argument("worker_id", help="Worker ID to resume")
    ck_cont.add_argument("--worktree", help="Override worktree path")
    ck_cont.add_argument("--executor", help="Executor for resumption (default: sonnet)")
    ck_cont.add_argument("--task-file", help="Resumption brief path")

    # validate-matrix
    vm_parser = subparsers.add_parser("validate-matrix", help="Validate matrix TOML")
    vm_parser.add_argument("matrix_path", help="Path to dispatch_matrix.toml")

    # doctor
    doctor_parser = subparsers.add_parser("doctor", help="Show live executor availability/health")
    doctor_parser.add_argument("--matrix", default=None, help="Override dispatch matrix path")
    doctor_parser.add_argument("--json", action="store_true", help="JSON output")
    doctor_parser.add_argument(
        "--probe", nargs="*", default=None, metavar="EXECUTOR",
        help="Live-probe lanes end-to-end through their real wrappers (~1 tiny "
             "model call each). With no names: all available lanes except "
             "openai-codex (whose OAuth refresh is single-use; name explicitly "
             "to probe).")

    # compact
    subparsers.add_parser("compact", help="Compact registry")

    args = parser.parse_args()

    if args.command == "task":
        cmd_start(args, "task")
    elif args.command == "breakout":
        cmd_start(args, "breakout")
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "kill":
        cmd_kill(args)
    elif args.command == "budget":
        cmd_budget(args)
    elif args.command == "completions":
        cmd_completions(args)
    elif args.command == "questions":
        cmd_questions(args)
    elif args.command == "route":
        cmd_route(args)
    elif args.command == "answer":
        cmd_answer(args)
    elif args.command == "checkpoint":
        cmd_checkpoint(args)
    elif args.command == "validate-matrix":
        cmd_validate_matrix(args)
    elif args.command == "doctor":
        cmd_doctor(args)
    elif args.command == "compact":
        cmd_compact(args)


def _add_start_args(parser, executor_names):
    """Add common arguments for task/breakout start."""
    choices = (executor_names + ["auto"]) if executor_names else None
    parser.add_argument("--executor", default="auto", choices=choices, help="Executor name, or auto")
    parser.add_argument("--task-file", help="Path to brief file")
    parser.add_argument("--task", help="Inline task string")
    parser.add_argument("--cwd", help="Working directory for worker")
    parser.add_argument("--slug", help="Short name for worker ID")

    # Nested dispatch args
    parser.add_argument("--parent-id", dest="parent_id", help="Parent worker ID")
    parser.add_argument("--parent-executor", dest="parent_executor", help="Parent executor name")
    parser.add_argument("--depth", type=int, default=0, help="Nesting depth")
    parser.add_argument("--budget-remaining", dest="budget_remaining", type=float, help="Remaining budget")
    parser.add_argument("--deadline", help="ISO-8601 deadline")


if __name__ == "__main__":
    main()
