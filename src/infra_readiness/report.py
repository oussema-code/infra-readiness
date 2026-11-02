"""Render the same results as readable text and an optional JSON artifact."""

from datetime import datetime, timezone
import json
from pathlib import Path

from .models import Result, Status, exit_code


def document(results: list[Result]):
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "exit_code": exit_code(results),
        "summary": {status.value: sum(result.status == status for result in results) for status in Status},
        "checks": [result.to_dict() for result in results],
    }


def readable(results: list[Result]) -> str:
    lines = [f"{r.status:7} {r.name} ({r.type}, {r.target}, {r.duration_ms:.1f} ms)\n"
             f"        {r.evidence}" for r in results]
    summary = ", ".join(f"{sum(r.status == status for r in results)} {status.value}" for status in Status)
    return "\n".join(lines + [f"Summary: {summary}; exit {exit_code(results)}"])


def write_json(path: Path, results: list[Result]):
    path.write_text(json.dumps(document(results), indent=2) + "\n", encoding="utf-8")
