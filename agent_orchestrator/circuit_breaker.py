"""
agent_orchestrator/circuit_breaker.py

Harness gate: CONSTITUTION.md Section 1.2.
Bounds every retryable loop to MAX_RETRIES (3) attempts per task, and reports
a terminal, loggable state when it trips. No loop in this codebase should
retry without going through this.
"""
from dataclasses import dataclass, field
from enum import Enum

from config.settings import HARNESS


class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # normal operation, retries allowed
    OPEN = "OPEN"             # tripped, no further retries permitted
    HALF_OPEN = "HALF_OPEN"   # optional: allow exactly one probe attempt


@dataclass
class CircuitBreaker:
    """
    One CircuitBreaker instance per task_id. Callers must construct a fresh
    one (or call reset()) when a genuinely new task begins.
    """
    task_id: str
    max_retries: int = HARNESS.MAX_RETRIES
    failure_count: int = 0
    state: CircuitState = field(default=CircuitState.CLOSED)
    last_error: str | None = None

    def record_failure(self, error: str) -> CircuitState:
        self.failure_count += 1
        self.last_error = error
        if self.failure_count >= self.max_retries:
            self.state = CircuitState.OPEN
        return self.state

    def record_success(self) -> None:
        self.failure_count = 0
        self.last_error = None
        self.state = CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    @property
    def attempts_remaining(self) -> int:
        return max(0, self.max_retries - self.failure_count)

    def reset(self) -> None:
        self.failure_count = 0
        self.last_error = None
        self.state = CircuitState.CLOSED

    def status_snapshot(self) -> dict:
        return {
            "task_id": self.task_id,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "max_retries": self.max_retries,
            "last_error": self.last_error,
        }
