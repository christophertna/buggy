"""
mcp_server/validators.py

Harness gate: CONSTITUTION.md Section 1.1.
Every write MUST pass validate_write() before reaching db_connector.
This module has no knowledge of the LLM or the orchestrator — it is a pure,
independently testable safety boundary.
"""
import re
from dataclasses import dataclass
from enum import Enum

from config.settings import HARNESS

_DESTRUCTIVE_UNSCOPED = re.compile(
    r"^\s*(DROP|TRUNCATE)\b", re.IGNORECASE
)
_WRITE_VERBS = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|REPLACE|ALTER|CREATE|DROP|TRUNCATE)\b",
    re.IGNORECASE,
)
_HAS_WHERE = re.compile(r"\bWHERE\b", re.IGNORECASE)
_TABLE_AFTER_VERB = re.compile(
    r"\b(?:UPDATE|INTO|FROM|TABLE)\s+`?([a-zA-Z0-9_]+)`?", re.IGNORECASE
)


class ValidationOutcome(str, Enum):
    ALLOWED = "ALLOWED"
    BLOCKED_UNPARAMETERIZED = "BLOCKED_UNPARAMETERIZED"
    BLOCKED_DESTRUCTIVE_UNSCOPED = "BLOCKED_DESTRUCTIVE_UNSCOPED"
    BLOCKED_PROTECTED_TABLE = "BLOCKED_PROTECTED_TABLE"
    BLOCKED_MISSING_WHERE = "BLOCKED_MISSING_WHERE"
    BLOCKED_ROW_ESTIMATE_TOO_HIGH = "BLOCKED_ROW_ESTIMATE_TOO_HIGH"
    NOT_A_WRITE = "NOT_A_WRITE"


@dataclass
class ValidationResult:
    outcome: ValidationOutcome
    reason: str

    @property
    def is_allowed(self) -> bool:
        return self.outcome == ValidationOutcome.ALLOWED


def is_write_statement(sql: str) -> bool:
    return bool(_WRITE_VERBS.match(sql.strip()))


def _looks_unparameterized(sql: str, params) -> bool:
    """
    Heuristic: if the SQL contains a quoted literal that looks like it was
    string-interpolated (as opposed to a %s / :name placeholder) and no
    params were supplied, treat it as unparameterized. This is intentionally
    conservative: false positives (blocking) are acceptable, false negatives
    are not.
    """
    has_placeholder = "%s" in sql or re.search(r":\w+", sql)
    if params:
        return False
    if has_placeholder and not params:
        # Placeholders present but no params bound — definitely unsafe.
        return True
    # No placeholders and no params: only acceptable for literal-free DDL.
    literal_pattern = re.compile(r"=\s*['\"]")
    return bool(literal_pattern.search(sql))


def _extract_table(sql: str) -> str | None:
    match = _TABLE_AFTER_VERB.search(sql)
    return match.group(1).lower() if match else None

def validate_read_only(sql: str) -> ValidationResult:
    """
    Harness gate for tools that must NEVER mutate data, regardless of what
    they're called with, mainly used by the Supabase client-data tool and the
    MySQL PDF-template tool (CONSTITUTION.md 1.6). Unlike validate_write,
    this doesn't check parameterization/scoping; it simply refuses anything
    that isnt a read.
    """
    if is_write_statement(sql):
        return ValidationResult(
            ValidationOutcome.BLOCKED_UNPARAMETERIZED,  # reuse: "blocked, unsafe"
            "This tool is read-only and rejects any mutating statement.",
        )
    return ValidationResult(ValidationOutcome.ALLOWED, "Read-only statement permitted.")

def validate_write(
    sql: str,
    params: tuple | dict | None = None,
    estimated_rows_affected: int | None = None,
    allow_protected: bool = False,
) -> ValidationResult:
    """
    The single choke point for all mutating SQL. Called by tools/sql_write.py
    before anything is sent to the database connector.
    """
    if not is_write_statement(sql):
        return ValidationResult(ValidationOutcome.NOT_A_WRITE, "Not a mutating statement.")

    if _DESTRUCTIVE_UNSCOPED.match(sql.strip()):
        return ValidationResult(
            ValidationOutcome.BLOCKED_DESTRUCTIVE_UNSCOPED,
            "DROP/TRUNCATE are never permitted from the agent loop.",
        )

    if _looks_unparameterized(sql, params):
        return ValidationResult(
            ValidationOutcome.BLOCKED_UNPARAMETERIZED,
            "Query must be parameterized; string-interpolated literals are rejected.",
        )

    table = _extract_table(sql)
    if table and table in HARNESS.PROTECTED_TABLES and not allow_protected:
        return ValidationResult(
            ValidationOutcome.BLOCKED_PROTECTED_TABLE,
            f"Table '{table}' is protected and requires human-reviewed override.",
        )

    verb_match = re.match(r"\s*(UPDATE|DELETE)\b", sql, re.IGNORECASE)
    if (
        verb_match
        and HARNESS.REQUIRE_WHERE_ON_MUTATION
        and not _HAS_WHERE.search(sql)
    ):
        return ValidationResult(
            ValidationOutcome.BLOCKED_MISSING_WHERE,
            "UPDATE/DELETE without a WHERE clause is blocked (unscoped mutation).",
        )

    if (
        estimated_rows_affected is not None
        and estimated_rows_affected > HARNESS.MAX_ROWS_AFFECTED
    ):
        return ValidationResult(
            ValidationOutcome.BLOCKED_ROW_ESTIMATE_TOO_HIGH,
            f"Estimated {estimated_rows_affected} rows affected exceeds "
            f"MAX_ROWS_AFFECTED={HARNESS.MAX_ROWS_AFFECTED}.",
        )

    return ValidationResult(ValidationOutcome.ALLOWED, "Passed all Harness checks.")
