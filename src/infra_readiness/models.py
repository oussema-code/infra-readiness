"""Shared result contract for evidence collected by probes."""

from dataclasses import asdict, dataclass
from enum import StrEnum


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Result:
    name: str
    type: str
    target: str
    status: Status
    duration_ms: float
    evidence: str
    error_category: str | None = None

    def to_dict(self):
        return asdict(self)


def exit_code(results: list[Result]) -> int:
    if not results:
        raise ValueError("cannot summarize an empty result set")
    if any(result.error_category == "tool_error" for result in results):
        return 3
    if any(result.status == Status.FAIL for result in results):
        return 1
    if any(result.status == Status.UNKNOWN for result in results):
        return 2
    return 0
