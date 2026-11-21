"""Retry queue: exponential backoff with jitter, then a dead-letter list. One SQLite file."""
import json
import random
import sqlite3
import threading
from datetime import datetime, timedelta

from eventlog import FileLock


def delay_seconds(attempt, rng=random.random):
    """2^attempt seconds, ±20%. attempt 0 waits about a second, then 2, 4, … capped at 60."""
    base = min(60.0, 2.0 ** attempt)
    return max(0.0, base + base * 0.2 * (rng() * 2 - 1))


class RetryQueue:
    def __init__(self, path, rng=random.random, max_attempts=4):
        self.path, self.rng, self.max_attempts = path, rng, max_attempts
        self._thread = threading.Lock()
        self._init()

    def _lock(self):
        return FileLock(self.path.with_suffix(".lock"), self._thread)

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock():
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS retries (
                        key TEXT PRIMARY KEY, payload TEXT NOT NULL, attempt INTEGER NOT NULL,
                        next_at TEXT NOT NULL, error TEXT NOT NULL)"""
                )
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS dead_letters (
                        key TEXT PRIMARY KEY, payload TEXT NOT NULL, error TEXT NOT NULL, at TEXT NOT NULL)"""
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def note(self, key, payload, error, now):
        """Queue a failed job once. A second note for the same key does not reset the wait."""
        when = (now + timedelta(seconds=delay_seconds(0, self.rng))).isoformat(timespec="seconds")
        with self._lock():
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT OR IGNORE INTO retries (key, payload, attempt, next_at, error) VALUES (?, ?, 0, ?, ?)",
                    (key, json.dumps(payload, ensure_ascii=False), when, error),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def claim(self, now, lease_seconds=120):
        """Due jobs. Each is leased so the next tick does not run it again before this attempt finishes."""
        stamp = now.isoformat(timespec="seconds")
        leased = (now + timedelta(seconds=lease_seconds)).isoformat(timespec="seconds")
        with self._lock():
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                rows = conn.execute("SELECT key, payload, attempt, error FROM retries WHERE next_at <= ?", (stamp,)).fetchall()
                for row in rows:
                    conn.execute("UPDATE retries SET next_at = ? WHERE key = ?", (leased, row["key"]))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()
        return [{"key": r["key"], "payload": json.loads(r["payload"]), "attempt": r["attempt"], "error": r["error"]}
                for r in rows]

    def fail(self, key, error, now):
        """Count one more failure. Returns 'dead' or 'retry'."""
        with self._lock():
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute("SELECT payload, attempt FROM retries WHERE key = ?", (key,)).fetchone()
                if row is None:
                    conn.execute("COMMIT")
                    return "missing"
                attempt = row["attempt"] + 1
                if attempt >= self.max_attempts:
                    conn.execute(
                        "INSERT OR REPLACE INTO dead_letters (key, payload, error, at) VALUES (?, ?, ?, ?)",
                        (key, row["payload"], error, now.isoformat(timespec="seconds")),
                    )
                    conn.execute("DELETE FROM retries WHERE key = ?", (key,))
                    conn.execute("COMMIT")
                    return "dead"
                when = (now + timedelta(seconds=delay_seconds(attempt, self.rng))).isoformat(timespec="seconds")
                conn.execute("UPDATE retries SET attempt = ?, next_at = ?, error = ? WHERE key = ?",
                             (attempt, when, error, key))
                conn.execute("COMMIT")
                return "retry"
            except Exception:
                conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def succeed(self, key):
        with self._lock():
            conn = self._connect()
            try:
                conn.execute("DELETE FROM retries WHERE key = ?", (key,))
            finally:
                conn.close()

    def open_count(self):
        with self._lock():
            conn = self._connect()
            try:
                return conn.execute("SELECT COUNT(*) FROM retries").fetchone()[0]
            finally:
                conn.close()

    def dead(self):
        with self._lock():
            conn = self._connect()
            try:
                rows = conn.execute("SELECT key, payload, error, at FROM dead_letters ORDER BY at").fetchall()
            finally:
                conn.close()
        return [{"key": r["key"], "payload": json.loads(r["payload"]), "error": r["error"], "at": r["at"]} for r in rows]
