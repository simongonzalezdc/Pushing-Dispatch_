"""Checkpoint protocol for advisor-reviewed phased breakouts.

A phased brief can opt into `CHECKPOINT: pause-for-review` after a phase's
COMMIT line. When the worker hits such a boundary it writes a checkpoint
file, exits in phase `awaiting_checkpoint`, and waits for the advisor to
review and resume with `cli.py checkpoint continue <worker-id>`.

Default behavior is unchanged -- briefs without CHECKPOINT directives run
through phases sequentially. The pause is strictly opt-in, per-phase.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


# Canonical checkpoints directory. Override via DISPATCH_CHECKPOINT_ROOT
# for tests or non-default layouts.
DEFAULT_CHECKPOINT_ROOT = Path(
    os.environ.get(
        "DISPATCH_ROOT",
        os.path.expanduser("~/.local/share/pushing-dispatch"),
    )
) / "checkpoints"


def checkpoint_root() -> Path:
    override = os.environ.get("DISPATCH_CHECKPOINT_ROOT")
    return Path(override) if override else DEFAULT_CHECKPOINT_ROOT


# Matches `CHECKPOINT: <directive>` lines. Directive is a short token
# (letters/digits/hyphens only) so garbage payloads surface as parse errors.
_CHECKPOINT_DIRECTIVE_RE = re.compile(r"^\s*CHECKPOINT:\s*([a-zA-Z0-9_-]+)\s*$")

# Matches phase headings: `## Phase <label>` or `### Phase <label>`.
_PHASE_HEADING_RE = re.compile(r"^\s*#{2,3}\s*Phase\s+([A-Za-z0-9_.-]+)")

VALID_DIRECTIVES = frozenset({"pause-for-review", "auto-continue"})


@dataclass
class PhaseDirective:
    """What the worker should do after finishing a phase."""
    phase: str
    directive: str  # "pause-for-review" or "auto-continue"


def parse_phase_directives(brief_text: str) -> list[PhaseDirective]:
    """Walk the brief and return every (phase_label, directive) pair.

    A phase with no explicit `CHECKPOINT:` line is treated as `auto-continue`.
    """
    lines = brief_text.splitlines()
    phases: list[tuple[str, list[str]]] = []
    current_label: str | None = None
    current_body: list[str] = []

    for line in lines:
        m = _PHASE_HEADING_RE.match(line)
        if m:
            if current_label is not None:
                phases.append((current_label, current_body))
            current_label = m.group(1)
            current_body = []
        else:
            if current_label is not None:
                current_body.append(line)

    if current_label is not None:
        phases.append((current_label, current_body))

    out: list[PhaseDirective] = []
    for label, body in phases:
        directive = "auto-continue"
        for line in body:
            dm = _CHECKPOINT_DIRECTIVE_RE.match(line)
            if dm:
                candidate = dm.group(1)
                if candidate in VALID_DIRECTIVES:
                    directive = candidate
                break  # first CHECKPOINT wins per phase
        out.append(PhaseDirective(phase=label, directive=directive))
    return out


def directive_for_phase(brief_text: str, phase_label: str) -> str:
    """Return the directive for a named phase, or 'auto-continue' if absent."""
    for pd in parse_phase_directives(brief_text):
        if pd.phase == phase_label:
            return pd.directive
    return "auto-continue"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_checkpoint_file(
    *,
    slug: str,
    phase: str,
    worker_id: str,
    commit_sha: str,
    what_i_did: str = "",
    files_committed: str = "",
    test_results: str = "",
    notes: str = "",
    next_phase: str = "",
    directive: str = "pause-for-review",
    root: Path | None = None,
) -> Path:
    """Write a checkpoint markdown file with YAML frontmatter + sections.

    Returns the written path. Creates the directory if missing.
    """
    base = root if root is not None else checkpoint_root()
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{slug}-{phase}.md"
    content = (
        "---\n"
        f"worker_id: {worker_id}\n"
        f"slug: {slug}\n"
        f"phase: {phase}\n"
        f"commit_sha: {commit_sha}\n"
        f"timestamp: {_now_iso()}\n"
        f"directive: {directive}\n"
        "---\n\n"
        f"# Checkpoint -- {slug} Phase {phase}\n\n"
        "## What I did\n\n"
        f"{what_i_did or '(none recorded)'}\n\n"
        "## What I committed\n\n"
        f"{files_committed or '(none recorded)'}\n\n"
        "## Test results\n\n"
        f"{test_results or '(none recorded)'}\n\n"
        "## Notes for advisor\n\n"
        f"{notes or '(none)'}\n\n"
        "## Next phase\n\n"
        f"{next_phase or '(none)'}\n"
    )
    path.write_text(content)
    return path


@dataclass
class AwaitingCheckpoint:
    path: Path
    worker_id: str
    slug: str
    phase: str
    commit_sha: str
    timestamp: str
    directive: str


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Tiny YAML frontmatter extractor (key: value lines only)."""
    if not text.startswith("---\n"):
        return {}
    body = text[4:]
    end = body.find("\n---\n")
    if end == -1:
        return {}
    out: dict[str, str] = {}
    for line in body[:end].splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip()
    return out


def list_awaiting_checkpoints(root: Path | None = None) -> list[AwaitingCheckpoint]:
    """Scan the checkpoints directory for files whose directive is pause-for-review.

    Returns the list sorted by timestamp (oldest first) so list output is stable.
    """
    base = root if root is not None else checkpoint_root()
    if not base.is_dir():
        return []
    out: list[AwaitingCheckpoint] = []
    for path in base.glob("*.md"):
        fm = _parse_frontmatter(path.read_text())
        if fm.get("directive") != "pause-for-review":
            continue
        out.append(
            AwaitingCheckpoint(
                path=path,
                worker_id=fm.get("worker_id", ""),
                slug=fm.get("slug", ""),
                phase=fm.get("phase", ""),
                commit_sha=fm.get("commit_sha", ""),
                timestamp=fm.get("timestamp", ""),
                directive=fm.get("directive", ""),
            )
        )
    out.sort(key=lambda c: c.timestamp)
    return out


def find_checkpoint_by_worker(
    worker_id: str, root: Path | None = None
) -> AwaitingCheckpoint | None:
    for c in list_awaiting_checkpoints(root=root):
        if c.worker_id == worker_id:
            return c
    return None


PAUSE_MARKER = "CHECKPOINT_PAUSE_REQUESTED"


def write_and_exit(
    *,
    slug: str,
    phase: str,
    worker_id: str,
    commit_sha: str,
    what_i_did: str = "",
    files_committed: str = "",
    test_results: str = "",
    notes: str = "",
    next_phase: str = "",
    root: Path | None = None,
) -> None:
    """Write checkpoint file, set status to awaiting_checkpoint, and exit.

    The enforcement layer for `CHECKPOINT: pause-for-review`.
    An orchestrator calls this at a pause boundary instead of writing the
    file manually and continuing to the next phase. Three effects:

    1. Checkpoint file written with `pause-for-review` directive.
    2. Worker's status row finalized to `awaiting_checkpoint` (terminal).
    3. Process exits with status 0 after printing PAUSE_MARKER.
    """
    from dispatch_lib import status_writer

    path = write_checkpoint_file(
        slug=slug,
        phase=phase,
        worker_id=worker_id,
        commit_sha=commit_sha,
        what_i_did=what_i_did,
        files_committed=files_committed,
        test_results=test_results,
        notes=notes,
        next_phase=next_phase,
        directive="pause-for-review",
        root=root,
    )
    status_writer.finalize(worker_id, "awaiting_checkpoint")
    print(f"{PAUSE_MARKER}: {slug} phase={phase} worker_id={worker_id}")
    print(f"checkpoint written: {path}")
    print("orchestrator must halt now -- do not dispatch further phases.")
    sys.exit(0)


def has_pause_for_review_for_worker(
    worker_id: str, root: Path | None = None
) -> bool:
    """True if any pause-for-review checkpoint exists for this worker_id."""
    return find_checkpoint_by_worker(worker_id, root=root) is not None


def archive_checkpoint(checkpoint: AwaitingCheckpoint) -> Path:
    """Move a consumed checkpoint file into a `_done/` subdir, timestamped.

    Called by `checkpoint continue` after re-dispatch succeeds.
    """
    done_dir = checkpoint.path.parent / "_done"
    done_dir.mkdir(parents=True, exist_ok=True)
    target = done_dir / f"{_now_iso().replace(':', '')}_{checkpoint.path.name}"
    checkpoint.path.rename(target)
    return target
