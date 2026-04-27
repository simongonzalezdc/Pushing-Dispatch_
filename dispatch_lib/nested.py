"""
Tree-walk utilities for nested dispatch.

Workers form a tree via parent_id pointers in the registry.
This module reconstructs trees from the flat registry and
provides kill-cascade, spend-rollup, and listing helpers.
"""

import json
import os
import signal
import time
from collections import defaultdict
from pathlib import Path

from .path_conventions import registry_path, status_path
from .status_writer import read_status, finalize, is_terminal


def build_tree(entries: list[dict]) -> dict:
    """Build parent->children map from registry entries.

    Args:
        entries: list of status dicts with worker_id and parent_id fields.

    Returns:
        {parent_id: [child_status_dict, ...]}
    """
    tree = defaultdict(list)
    for entry in entries:
        pid = entry.get("parent_id")
        if pid:
            tree[pid].append(entry)
    return dict(tree)


def children_of(worker_id: str, entries: list[dict]) -> list[dict]:
    """Get direct children of a worker."""
    return [e for e in entries if e.get("parent_id") == worker_id]


def tree_for(worker_id: str, entries: list[dict]) -> list[dict]:
    """Get all descendants of a worker (breadth-first)."""
    tree = build_tree(entries)
    result = []
    queue = [worker_id]
    seen = set()
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        kids = tree.get(current, [])
        for kid in kids:
            kid_id = kid["worker_id"]
            result.append(kid)
            queue.append(kid_id)
    return result


def find_root(worker_id: str, entries: list[dict]) -> str:
    """Walk parent pointers to find the root of a worker's tree."""
    parent_map = {e["worker_id"]: e.get("parent_id") for e in entries}
    current = worker_id
    seen = set()
    while current in parent_map and parent_map[current] and current not in seen:
        seen.add(current)
        current = parent_map[current]
    return current


def kill_cascade(worker_id: str, entries: list[dict]) -> list[str]:
    """Kill a worker and all its descendants, bottom-up.

    Bottom-up ordering prevents orphan races: leaves die first,
    then their parents. This ensures children are cleaned up
    before their tracking anchor disappears.

    Returns: list of killed worker IDs.
    """
    # Collect full subtree
    descendants = tree_for(worker_id, entries)

    # Sort by depth descending (leaves first)
    to_kill = sorted(descendants, key=lambda e: e.get("depth", 0), reverse=True)

    # Add the target worker itself at the end
    target = next((e for e in entries if e["worker_id"] == worker_id), None)
    if target:
        to_kill.append(target)

    killed = []
    for entry in to_kill:
        wid = entry["worker_id"]
        pid = entry.get("pid")

        # Try to terminate the process
        if pid:
            _kill_process(pid)

        # Finalize status
        finalize(wid, "killed", exit_code=-15, error_summary=f"Killed via cascade from {worker_id}")
        killed.append(wid)

    return killed


def tree_spend(worker_id: str, entries: list[dict], budget_entries: list[dict]) -> float:
    """Sum spend for a worker and all its descendants."""
    tree_ids = {worker_id} | {e["worker_id"] for e in tree_for(worker_id, entries)}
    total = 0.0
    for be in budget_entries:
        if be.get("worker_id") in tree_ids:
            total += be.get("cost", 0.0)
    return total


def format_tree(entries: list[dict], root_ids: list[str] = None) -> str:
    """Format workers as an indented tree for display.

    Args:
        entries: all worker status entries
        root_ids: specific roots to display (default: all roots)

    Returns:
        Formatted tree string
    """
    tree_map = build_tree(entries)
    entry_map = {e["worker_id"]: e for e in entries}

    if root_ids is None:
        # Find roots (workers with no parent or parent not in entries)
        all_ids = {e["worker_id"] for e in entries}
        root_ids = [
            e["worker_id"]
            for e in entries
            if not e.get("parent_id") or e["parent_id"] not in all_ids
        ]

    lines = []
    for rid in root_ids:
        if rid in entry_map:
            _format_node(entry_map[rid], tree_map, entry_map, lines, prefix="", is_last=True)

    return "\n".join(lines)


def _format_node(entry, tree_map, entry_map, lines, prefix, is_last):
    """Recursively format a tree node."""
    connector = "" if not prefix else ("\\-- " if is_last else "|-- ")
    wid = entry["worker_id"]
    executor = entry.get("executor", "?")
    mode = entry.get("mode", "?")
    phase = entry.get("current_phase", "?")
    depth_indicator = f" (depth {entry.get('depth', 0)})" if entry.get("depth", 0) > 0 else ""

    lines.append(f"{prefix}{connector}{wid}  {executor}  {mode}  {phase}{depth_indicator}")

    children = tree_map.get(wid, [])
    for i, child in enumerate(children):
        child_entry = entry_map.get(child["worker_id"], child)
        child_prefix = prefix + ("    " if is_last else "|   ")
        _format_node(child_entry, tree_map, entry_map, lines, child_prefix, i == len(children) - 1)


def _kill_process(pid: int):
    """Attempt to terminate a process. SIGTERM with 5s grace, then SIGKILL."""
    try:
        os.kill(pid, signal.SIGTERM)
        # Brief grace period
        for _ in range(50):
            time.sleep(0.1)
            try:
                os.kill(pid, 0)  # Check if alive
            except ProcessLookupError:
                return  # Already dead
        # Force kill
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # Already dead
    except PermissionError:
        pass  # Cannot kill (different user)
