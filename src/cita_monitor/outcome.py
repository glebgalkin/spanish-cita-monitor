"""Result of a single monitoring run."""

from dataclasses import dataclass
from enum import StrEnum


class Outcome(StrEnum):
    APPOINTMENTS_FOUND = "APPOINTMENTS_FOUND"
    NO_APPOINTMENTS = "NO_APPOINTMENTS"
    BLOCKED = "BLOCKED"
    PORTAL_ERROR = "PORTAL_ERROR"
    UNAVAILABLE = "UNAVAILABLE"
    FLOW_CHANGED = "FLOW_CHANGED"

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self]


EXIT_CODES = {
    Outcome.NO_APPOINTMENTS: 0,
    Outcome.APPOINTMENTS_FOUND: 10,
    Outcome.BLOCKED: 20,
    Outcome.PORTAL_ERROR: 21,
    Outcome.UNAVAILABLE: 22,
    Outcome.FLOW_CHANGED: 30,
}


@dataclass(frozen=True)
class RunResult:
    outcome: Outcome
    detail: str
    step: str = ""
