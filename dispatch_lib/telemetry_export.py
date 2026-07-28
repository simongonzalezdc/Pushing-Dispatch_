"""Read-only HTML export for utilization snapshots."""

from __future__ import annotations

import html
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .utilization_schema import validate_snapshot


def render_html(snapshots: Iterable[dict[str, Any]], output_path: Path,
                assignments: Iterable[dict[str, Any]] | None = None) -> Path:
    """Atomically render validated snapshots without touching Dispatch state."""
    rows = []
    for snapshot in snapshots:
        validate_snapshot(snapshot)
        metric = snapshot["metric"]
        cells = [
            snapshot["provider_id"],
            snapshot["executor_id"],
            snapshot["provider_class"],
            f'{metric["numerator"]} / {metric["denominator"]}',
            f'{metric["value"]:.1%}',
            snapshot["status"],
            snapshot["freshness_at"],
            snapshot["confidence"],
            snapshot["recommendation"],
            snapshot.get("exclusion_reason", ""),
            snapshot.get("last_outcome", "unknown"),
            snapshot.get("renewal_advisory", "unknown"),
            ", ".join(snapshot.get("provenance", {}).get("source_artifacts", [])),
        ]
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in cells) + "</tr>")
    assignment_rows = []
    for assignment in assignments or []:
        assignment_rows.append(
            "<tr>" + "".join(
                f"<td>{html.escape(str(assignment.get(key, '')))}</td>"
                for key in ("job", "executor", "status")
            ) + "</tr>"
        )
    assignment_section = """
<h2>Recurring work plan</h2><table><thead><tr><th>Job family</th><th>Dispatch-selected executor</th><th>Status</th></tr></thead><tbody>""" + "".join(assignment_rows) + "</tbody></table>" if assignment_rows else ""
    document = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Inference Utilization Control Plane</title>
<style>:root{color-scheme:light dark;--bg:#f4f2ea;--card:#fffdf8;--ink:#17211b;--line:#7b857e;--head:#e5ebe6}*{box-sizing:border-box}body{font:16px/1.5 system-ui;max-width:1100px;margin:auto;padding:2rem;background:var(--bg);color:var(--ink)}main{background:var(--card);padding:clamp(1rem,4vw,3rem);border:1px solid var(--line);border-radius:1rem}table{border-collapse:collapse;width:100%;margin-bottom:2rem}th,td{border:1px solid var(--line);padding:.55rem;text-align:left;vertical-align:top}th{background:var(--head);color:#111}@media(prefers-color-scheme:dark){:root{--bg:#101613;--card:#18201c;--ink:#edf3ee;--line:#69776e;--head:#dfe8e1}}@media(max-width:700px){body{padding:.5rem}main{padding:.75rem}table{display:block;overflow:auto}}@media print{body,main{background:#fff;color:#000;border:0;padding:0}table{font-size:10pt}}</style>
</head><body><main><h1>Inference Utilization Control Plane</h1>
<p>This report is read-only. Cancellation and financial changes always require explicit human confirmation.</p>
<table><thead><tr><th>Provider</th><th>Executor</th><th>Class</th><th>Utilization</th><th>Rate</th><th>Status</th><th>Freshness</th><th>Confidence</th><th>Recommendation</th><th>Exclusion reason</th><th>Last outcome</th><th>Renewal status</th><th>Provenance</th></tr></thead>
<tbody>""" + "".join(rows) + "</tbody></table>" + assignment_section + "</main></body></html>\n"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=output_path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(document)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, output_path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return output_path
