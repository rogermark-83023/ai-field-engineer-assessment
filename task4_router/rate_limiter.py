import asyncio
import sqlite3
import time
from contextlib import closing
from pathlib import Path

class RateLimiter:
    def __init__(self, db_path, limit=50_000, window=60, clock=None):
        self.db_path = Path(db_path)
        self.limit = limit
        self.window = window
        self.clock = clock or time.time

    async def setup(self):
        await asyncio.to_thread(self._setup)

    def _setup(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with closing(sqlite3.connect(self.db_path, timeout=10)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS token_usage ("
                "id INTEGER PRIMARY KEY, "
                "tenant TEXT NOT NULL, "
                "tokens INTEGER NOT NULL, "
                "created_at REAL NOT NULL)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_token_usage_tenant_time "
                "ON token_usage (tenant, created_at)"
            )
            db.commit()

    async def reserve(self, tenant, tokens):
        if not isinstance(tenant, str) or not tenant.strip():
            raise ValueError("Invalid tenant")
        if type(tokens) is not int or tokens <= 0:
            raise ValueError("Tokens must be a positive integer")
        if tokens > self.limit:
            return None

        return await asyncio.to_thread(self._reserve, tenant, tokens)

    def _reserve(self, tenant, tokens):
        with closing(sqlite3.connect(self.db_path, timeout=10, isolation_level=None)) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                now = self.clock()
                cutoff = now - self.window

                db.execute(
                    "DELETE FROM token_usage WHERE created_at <= ?",
                    (cutoff,)
                )

                used = db.execute(
                    "SELECT COALESCE(SUM(tokens), 0) FROM token_usage "
                    "WHERE tenant = ? AND created_at > ?",
                    (tenant, cutoff)
                ).fetchone()[0]

                if used + tokens > self.limit:
                    db.execute("ROLLBACK")
                    return None

                cursor = db.execute(
                    "INSERT INTO token_usage (tenant, tokens, created_at) "
                    "VALUES (?, ?, ?)",
                    (tenant, tokens, now)
                )

                db.execute("COMMIT")
                return cursor.lastrowid

            except Exception:
                db.execute("ROLLBACK")
                raise

    async def used(self, tenant):
        return await asyncio.to_thread(self._used, tenant)

    def _used(self, tenant):
        with closing(sqlite3.connect(self.db_path, timeout=10)) as db:
            return db.execute(
                "SELECT COALESCE(SUM(tokens), 0) FROM token_usage "
                "WHERE tenant = ? AND created_at > ?",
                (tenant, self.clock() - self.window)
            ).fetchone()[0]

    async def reconcile(self, reservation_id, actual_tokens):
        if type(actual_tokens) is not int or actual_tokens <= 0:
            raise ValueError("Invalid token usage")

        return await asyncio.to_thread(
            self._reconcile, reservation_id, actual_tokens
        )

    def _reconcile(self, reservation_id, actual_tokens):
        with closing(sqlite3.connect(
            self.db_path, timeout=10, isolation_level=None
        )) as db:
            db.execute("BEGIN IMMEDIATE")

            try:
                row = db.execute(
                    "SELECT tenant FROM token_usage WHERE id = ?",
                    (reservation_id,)
                ).fetchone()

                if row is None:
                    raise ValueError("Reservation not found")

                db.execute(
                    "UPDATE token_usage SET tokens = ? WHERE id = ?",
                    (actual_tokens, reservation_id)
                )

                used = db.execute(
                    "SELECT COALESCE(SUM(tokens), 0) FROM token_usage "
                    "WHERE tenant = ? AND created_at > ?",
                    (row[0], self.clock() - self.window)
                ).fetchone()[0]

                db.execute("COMMIT")
                return used <= self.limit

            except Exception:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    async def release(self, reservation_id):
        await asyncio.to_thread(self._release, reservation_id)

    def _release(self, reservation_id):
        with closing(sqlite3.connect(self.db_path, timeout=10)) as db:
            db.execute(
                "DELETE FROM token_usage WHERE id = ?",
                (reservation_id,)
            )
            db.commit()
