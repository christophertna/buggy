"""
config/settings.py

Central, env-driven configuration. Nothing secret is hardcoded here.
This module also holds the Harness constants referenced by CONSTITUTION.md —
keep the two in sync if you ever change them.
"""
import os
from dataclasses import dataclass, field


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class DBSettings:
    host: str = os.environ.get("MYSQL_HOST", "127.0.0.1")
    port: int = _env_int("MYSQL_PORT", 3306)
    user: str = os.environ.get("MYSQL_USER", "agent_user")
    password: str = os.environ.get("MYSQL_PASSWORD", "")
    database: str = os.environ.get("MYSQL_DATABASE", "app_db")
    connect_timeout: int = _env_int("MYSQL_CONNECT_TIMEOUT", 5)


@dataclass(frozen=True)
class HarnessSettings:
    # Constitutional constant — see CONSTITUTION.md Section 1.2.
    # Do not tune this without updating the Constitution.
    MAX_RETRIES: int = 3

    # Section 1.1 — write validation limits
    MAX_ROWS_AFFECTED: int = _env_int("MAX_ROWS_AFFECTED", 500)
    PROTECTED_TABLES: tuple = field(
        default_factory=lambda: tuple(
            _env_list("PROTECTED_TABLES", ["users", "payments", "audit_log"])
        )
    )
    REQUIRE_WHERE_ON_MUTATION: bool = True


@dataclass(frozen=True)
class LLMSettings:
    api_key: str = os.environ.get("OPENAI_API_KEY", "")
    model: str = os.environ.get("OPENAI_MODEL", "gpt-4.1")
    temperature: float = float(os.environ.get("OPENAI_TEMPERATURE", "0.1"))


@dataclass(frozen=True)
class PathSettings:
    tasks_file: str = os.environ.get("TASKS_FILE", "tasks.json")
    history_log: str = os.environ.get("HISTORY_LOG", "history.log")


DB = DBSettings()
HARNESS = HarnessSettings()
LLM = LLMSettings()
PATHS = PathSettings()
