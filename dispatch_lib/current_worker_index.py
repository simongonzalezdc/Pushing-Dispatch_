"""Publish a bounded, sanitized discovery index for current worker statuses."""

from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import re
import stat
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .path_conventions import dispatch_root, status_dir
from .status_writer import PHASES, is_terminal

WORKER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
INDEX_NAME = "current-workers.json"
LOCK_NAME = ".current-workers.lock"


class IndexBusy(RuntimeError):
    """Another producer owns the current-worker publication cycle."""


def _acquire_lock(owner_root: Path) -> int:
    """Acquire the fixed same-owner lock without following or deleting it."""
    owner_root.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(owner_root / LOCK_NAME, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid():
            raise PermissionError("unsafe current-worker lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise IndexBusy("current-worker index producer is busy") from None
            raise
        return fd
    except BaseException:
        os.close(fd)
        raise


@dataclass(frozen=True)
class Limits:
    entries: int = 8192
    bytes: int = 32 * 1024 * 1024
    file_bytes: int = 64 * 1024
    seconds: float = 2.0
    published: int = 128


def _stamp(now: float) -> str:
    return datetime.fromtimestamp(now, timezone.utc).isoformat().replace("+00:00", "Z")


def _directory_generation(fd: int) -> tuple[int, int, int]:
    value = os.fstat(fd)
    return value.st_dev, value.st_ino, value.st_mtime_ns


def build_index(
    root: Path, *, now=time.time, monotonic=time.monotonic, limits: Limits = Limits()
) -> dict:
    """Build one bounded snapshot. Status content remains authoritative."""
    started_wall, started_clock = now(), monotonic()
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(root, flags)
    try:
        before = _directory_generation(fd)
        candidates, checkpoints = [], []
        counts = {
            key: 0
            for key in (
                "scanned",
                "valid",
                "malformed",
                "terminal",
                "nonterminal",
                "awaiting_checkpoint",
                "phase_unknown",
                "published",
                "omitted",
            )
        }
        bytes_read = 0
        stop_reason = None
        with os.scandir(fd) as entries:
            for entry in entries:
                if monotonic() - started_clock >= limits.seconds:
                    stop_reason = "TIME_LIMIT"
                    break
                if counts["scanned"] >= limits.entries:
                    stop_reason = "ENTRY_LIMIT"
                    break
                counts["scanned"] += 1
                if not entry.name.endswith(".json") or not WORKER_ID.fullmatch(
                    entry.name[:-5]
                ):
                    counts["malformed"] += 1
                    continue
                child = None
                try:
                    child = os.open(
                        entry.name,
                        os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=fd,
                    )
                    info = os.fstat(child)
                    if (
                        not stat.S_ISREG(info.st_mode)
                        or info.st_size > limits.file_bytes
                    ):
                        counts["malformed"] += 1
                        continue
                    if (
                        bytes_read + min(info.st_size, limits.file_bytes + 1)
                        > limits.bytes
                    ):
                        stop_reason = "BYTE_LIMIT"
                        break
                    raw = os.read(child, limits.file_bytes + 1)
                    bytes_read += len(raw)
                    if len(raw) > limits.file_bytes:
                        counts["malformed"] += 1
                        continue
                    value = json.loads(raw)
                except (
                    OSError,
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                    TypeError,
                    ValueError,
                ):
                    counts["malformed"] += 1
                    continue
                finally:
                    if child is not None:
                        os.close(child)
                worker_id = entry.name[:-5]
                if not isinstance(value, dict) or value.get("worker_id") != worker_id:
                    counts["malformed"] += 1
                    continue
                counts["valid"] += 1
                phase = value.get("current_phase")
                if phase in PHASES and is_terminal(phase):
                    counts["terminal"] += 1
                    continue
                if phase not in PHASES:
                    counts["phase_unknown"] += 1
                else:
                    counts["nonterminal"] += 1
                    if phase == "awaiting_checkpoint":
                        counts["awaiting_checkpoint"] += 1
                item = (info.st_mtime_ns, worker_id)
                candidates.append(item)
                if phase == "awaiting_checkpoint":
                    checkpoints.append(item)
        after = _directory_generation(fd)
    finally:
        os.close(fd)

    candidates.sort(key=lambda item: (-item[0], item[1]))
    checkpoints.sort(key=lambda item: (-item[0], item[1]))
    ids = [item[1] for item in candidates[: limits.published]]
    published_ids = set(ids)
    checkpoint_ids = [item[1] for item in checkpoints if item[1] in published_ids]
    counts["published"] = len(ids)
    counts["omitted"] = max(0, len(candidates) - len(ids))
    consistent = before == after
    truncated = stop_reason is not None or counts["omitted"] > 0
    return {
        "schema_version": 1,
        "scan_started_at": _stamp(started_wall),
        "generated_at": _stamp(now()),
        "source_generation": {
            "device": before[0],
            "inode": before[1],
            "mtime_ns_before": before[2],
            "mtime_ns_after": after[2],
            "consistent": consistent,
        },
        "candidate_worker_ids": ids,
        "awaiting_checkpoint_worker_ids": checkpoint_ids,
        "counts": counts,
        "coverage": {
            "complete": consistent and not truncated,
            "truncated": truncated,
            "stop_reason": stop_reason
            or ("PUBLISH_LIMIT" if counts["omitted"] else None),
            "bytes_read": bytes_read,
            "limits": {
                "entries": limits.entries,
                "bytes": limits.bytes,
                "file_bytes": limits.file_bytes,
                "seconds": limits.seconds,
                "published": limits.published,
            },
        },
    }


def publish_index(
    *,
    root: Path | None = None,
    output: Path | None = None,
    now=time.time,
    monotonic=time.monotonic,
    limits: Limits = Limits(),
    build=build_index,
) -> dict:
    """Build, retry one raced scan, then durably replace the fixed index file."""
    owner_root = dispatch_root().resolve()
    root = status_dir() if root is None else Path(root)
    output = owner_root / INDEX_NAME if output is None else Path(output)
    if output != owner_root / INDEX_NAME:
        raise ValueError("index output must be DISPATCH_ROOT/current-workers.json")
    lock_fd = _acquire_lock(owner_root)
    try:
        result = build(root, now=now, monotonic=monotonic, limits=limits)
        if not result["source_generation"]["consistent"]:
            result = build(root, now=now, monotonic=monotonic, limits=limits)
        fd, temporary = tempfile.mkstemp(prefix=f".{INDEX_NAME}.", dir=owner_root)
        backup = f"{temporary}.old"
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(result, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            had_old_index = output.exists()
            if had_old_index:
                os.link(output, backup, follow_symlinks=False)
            os.replace(temporary, output)
            directory_fd = os.open(
                owner_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            )
            try:
                os.fsync(directory_fd)
            except BaseException:
                if had_old_index:
                    os.replace(backup, output)
                else:
                    os.unlink(output)
                raise
            finally:
                os.close(directory_fd)
            if had_old_index:
                os.unlink(backup)
        except BaseException:
            for artifact in (temporary, backup):
                try:
                    os.unlink(artifact)
                except FileNotFoundError:
                    pass
            raise
        return result
    finally:
        os.close(lock_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Publish the bounded current-worker index"
    )
    parser.parse_args(argv)
    try:
        result = publish_index()
    except IndexBusy:
        print(json.dumps({"status": "busy", "index_unchanged": True}))
        return 75
    print(
        json.dumps(
            {
                "generated_at": result["generated_at"],
                "coverage": result["coverage"],
                "counts": result["counts"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
