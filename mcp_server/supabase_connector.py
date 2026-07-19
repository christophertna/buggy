"""
mcp_server/supabase_connector.py

Read-only connector to the Supabase Postgres instance (client profile data).
Mirrors db_connector.py's shape deliberately, but intentionally exposes NO
write method. This connector is the client-data *source*, never a target.
If you ever need to write back to Supabase, that is a new, explicit decision
requiring its own Harness review (CONSTITUTION.md Section 3), not an
extension of this class.
"""
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from config.settings import SUPABASE


class SupabaseConnector:
    def __init__(self):
        self._conn = None

    def _connect(self):
        if self._conn is not None and not self._conn.closed:
            return self._conn
        self._conn = psycopg2.connect(
            host=SUPABASE.host,
            port=SUPABASE.port,
            user=SUPABASE.user,
            password=SUPABASE.password,
            dbname=SUPABASE.database,
            sslmode=SUPABASE.sslmode,
            connect_timeout=SUPABASE.connect_timeout,
        )
        self._conn.autocommit = False
        return self._conn

    @contextmanager
    def cursor(self):
        conn = self._connect()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield cur
        finally:
            cur.close()

    def execute_read(self, sql: str, params: tuple | dict | None = None) -> list[dict]:
        """SELECT only. No commit path exists on this connector by design."""
        with self.cursor() as cur:
            cur.execute(sql, params or ())
            return [dict(row) for row in cur.fetchall()]

    def close(self):
        if self._conn is not None and not self._conn.closed:
            self._conn.close()


supabase_db = SupabaseConnector()