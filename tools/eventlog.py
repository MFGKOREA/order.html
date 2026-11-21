"""Event-sourced ledger. SQLite WAL is the store. 대화.txt is a mirror, not the store.

One writer: an in-process lock plus an exclusive file lock, and BEGIN IMMEDIATE for the insert.
The idempotency key is the line itself, so a replay or a second hub process does not double it.
"""
import hashlib
import os
import sqlite3
import threading
from datetime import datetime
from pathlib import Path


def line_key(line):
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


class FileLock:
    """Exclusive lock. Threads in this process share `_thread`; other processes share the file."""

    def __init__(self, path, thread_lock):
        self.path, self.thread_lock, self.fh = Path(path), thread_lock, None

    def __enter__(self):
        self.thread_lock.acquire()
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.fh = open(self.path, "a+")
            if self.fh.seek(0, os.SEEK_END) == 0:
                self.fh.write(" ")
                self.fh.flush()
            self.fh.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX)
        except Exception:
            self.thread_lock.release()
            raise
        return self

    def __exit__(self, *exc):
        try:
            if os.name == "nt":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        finally:
            self.fh.close()
            self.thread_lock.release()


class EventLog:
    def __init__(self, db_path, text_path):
        self.db_path, self.text_path = Path(db_path), Path(text_path)
        self._thread = threading.Lock()
        self._init()
        with self._lock():
            if self._count() == 0:
                for line in self._text_lines():
                    self._insert(line)  # migration: the file is already the mirror
            else:
                self._repair()

    def _lock(self):
        return FileLock(self.db_path.with_suffix(".lock"), self._thread)

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=5, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock():
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY,
                        idempotency_key TEXT NOT NULL UNIQUE,
                        at TEXT NOT NULL,
                        request_id TEXT NOT NULL,
                        frm TEXT NOT NULL,
                        to_who TEXT NOT NULL,
                        status TEXT NOT NULL,
                        body TEXT NOT NULL,
                        line TEXT NOT NULL
                    )"""
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

    def _text_lines(self):
        try:
            return [line.strip() for line in self.text_path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        except FileNotFoundError:
            return []

    def _count(self):
        conn = self._connect()
        try:
            return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        finally:
            conn.close()

    def count(self):
        with self._lock():
            return self._count()

    def _insert(self, line, fields=None):
        """Insert under the caller's lock. Returns True when this line is new. Does not touch the text file."""
        key = line_key(line)
        fields = fields or _fields(line)
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                """INSERT OR IGNORE INTO events
                   (idempotency_key, at, request_id, frm, to_who, status, body, line)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (key, datetime.now().isoformat(timespec="seconds"),
                 fields["id"], fields["from"], fields["to"], fields["status"], fields["body"], line),
            )
            conn.execute("COMMIT")
            return cur.rowcount == 1
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def add(self, line, fields):
        """Atomic insert. A new event is appended to the text mirror. A repeat is a no-op."""
        with self._lock():
            if not self._insert(line, fields):
                return False
            self.text_path.parent.mkdir(parents=True, exist_ok=True)
            with self.text_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            return True

    def poll_new(self):
        """Lines someone else appended to the mirror, now stored. Already-stored lines are skipped."""
        found = []
        with self._lock():
            conn = self._connect()
            try:
                known = {row[0] for row in conn.execute("SELECT line FROM events")}
            finally:
                conn.close()
            for line in self._text_lines():
                if line in known:
                    continue
                if self._insert(line):
                    found.append(line)
                    known.add(line)
        return found

    def _repair(self):
        """Append store lines the mirror lost, in order. Caller holds the lock."""
        have = set(self._text_lines())
        conn = self._connect()
        try:
            missing = [row[0] for row in conn.execute("SELECT line FROM events ORDER BY id") if row[0] not in have]
        finally:
            conn.close()
        if not missing:
            return
        self.text_path.parent.mkdir(parents=True, exist_ok=True)
        with self.text_path.open("a", encoding="utf-8") as handle:
            handle.write("".join(line + "\n" for line in missing))

    def next_rule_id(self, now):
        day = now.strftime("%Y%m%d")
        prefix = f"R-{day}-"
        with self._lock():
            conn = self._connect()
            try:
                rows = conn.execute("SELECT request_id FROM events WHERE request_id LIKE ?", (prefix + "%",)).fetchall()
            finally:
                conn.close()
        n = 0
        for (rid,) in rows:
            try:
                n = max(n, int(rid[len(prefix):]))
            except ValueError:
                pass
        return f"{prefix}{n + 1:03d}"

    def recent(self, n=12):
        with self._lock():
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT at, request_id, frm, to_who, status, body FROM events ORDER BY id DESC LIMIT ?", (n,)
                ).fetchall()
            finally:
                conn.close()
        return [{"at": r["at"], "id": r["request_id"], "from": r["frm"], "to": r["to_who"],
                 "status": r["status"], "body": r["body"]} for r in rows]

    def open_to(self, who, status="대기"):
        """Request ids whose latest event is still `status` and addressed to `who`."""
        with self._lock():
            conn = self._connect()
            try:
                rows = conn.execute(
                    """SELECT request_id, to_who, status FROM events
                       WHERE id IN (SELECT MAX(id) FROM events GROUP BY request_id)"""
                ).fetchall()
            finally:
                conn.close()
        return [r["request_id"] for r in rows if r["to_who"] == who and r["status"] == status]


def _fields(line):
    parts = [part.strip() for part in line.split("|", 4)]
    if len(parts) != 5:
        return {"id": "?", "from": "?", "to": "?", "status": "완료", "body": line}
    return {"id": parts[0], "from": parts[1], "to": parts[2], "status": parts[3], "body": parts[4]}
