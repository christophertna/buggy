"""
mcp_server/db_connector.py

Thin, boring wrapper around the MySQL connection. Deliberately does NOT know
about the LLM, the orchestrator, or task state — it only knows how to talk to
MySQL 9.2 safely, and it always uses parameterized queries.

Uses pymysql (pure Python, no compiled deps) — swap for mysql-connector-python
if you prefer, the interface below is small enough to keep either way.
"""
from contextlib import contextmanager

import pymysql
import pymysql.cursors

from config.settings import DB


class DBConnector:
    def __init__(self):
        self._conn = None

    def _connect(self):
        if self._conn is not None and self._conn.open:
            return self._conn
        self._conn = pymysql.connect(
            host=DB.host,
            port=DB.port,
            user=DB.user,
            password=DB.password,
            database=DB.database,
            connect_timeout=DB.connect_timeout,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )
        return self._conn

    @contextmanager
    def cursor(self):
        conn = self._connect()
        cur = conn.cursor()
        try:
            yield cur
        finally:
            cur.close()

    def execute_read(self, sql: str, params: tuple | dict | None = None) -> list[dict]:
        """SELECT / SHOW / EXPLAIN only. No commit needed."""
        with self.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()

    def estimate_rows_affected(self, sql: str, params: tuple | dict | None = None) -> int | None:
        """
        Best-effort row estimate for UPDATE/DELETE via EXPLAIN, used by the
        Harness validator to enforce MAX_ROWS_AFFECTED. Returns None if it
        can't be estimated (validator should treat that conservatively).
        """
        try:
            explain_sql = "EXPLAIN " + sql
            with self.cursor() as cur:
                cur.execute(explain_sql, params or ())
                rows = cur.fetchall()
            return sum(r.get("rows", 0) or 0 for r in rows)
        except Exception:
            return None

    def execute_write(self, sql: str, params: tuple | dict | None = None) -> int:
        """
        Executes an already-validated mutating statement. Callers MUST have
        run this through mcp_server.validators.validate_write first — this
        method does not re-validate, by design (single responsibility).
        """
        conn = self._connect()
        with self.cursor() as cur:
            affected = cur.execute(sql, params or ())
            conn.commit()
            return affected

    def close(self):
        if self._conn is not None and self._conn.open:
            self._conn.close()


db = DBConnector()
