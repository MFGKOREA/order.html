#!/usr/bin/env python3
"""Pickle's hub: one resident process on the store PC that keeps every answer ready.

Files in the Drive folder Pickle reads (--drive):
  재고.txt 매출.txt 입고.txt BOH.txt   ready-made answers, rewritten when the cache changes
  작업.txt                            the action queue; 레미 works through the 접수 lines
  요청.txt                            requests, one per line, appended by Pickle (or anyone)
  답.txt                              the latest answers, each under "> request"

Requests can also be typed straight into the hub's window.

Usage: python3 tools/hub.py --drive "<Drive folder Pickle reads>" [--ai]
"""
import argparse
import hashlib
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_board  # noqa: E402
import pickle_relay as pr  # noqa: E402
import router  # noqa: E402

INBOX, OUTBOX, TASKS = "요청.txt", "답.txt", "작업.txt"
KEEP_ANSWERS = 5  # 답.txt holds only the latest answers (~280 tokens at most), so Pickle reads few tokens


def _digest(lines):
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


class Inbox:
    """Hands out each new line of the request file exactly once, also across restarts.

    The file is append-only. Lines already there when the hub first starts are history. If the
    file is rewritten instead of appended to (cleared, an old line edited), its current lines are
    treated as handled, so a request is never executed twice; lines added after that count.
    """

    def __init__(self, path, state_path, log=None):
        self.path, self.state_path, self.log = Path(path), Path(state_path), log or sys.stderr
        self._stamp = None
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.count, self.digest = state["count"], state["digest"]
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            self._save(self._read())  # first run ever: start from the current end

    def _read(self):
        try:
            return self.path.read_text(encoding="utf-8-sig").splitlines()
        except FileNotFoundError:
            return []

    def _save(self, lines):
        self.count, self.digest = len(lines), _digest(lines)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({"count": self.count, "digest": self.digest}), encoding="utf-8")

    def poll(self):
        try:
            st = self.path.stat()
        except FileNotFoundError:
            return []
        if (st.st_mtime_ns, st.st_size) == self._stamp:
            return []
        self._stamp = (st.st_mtime_ns, st.st_size)
        lines = self._read()
        if not any(line.strip() for line in lines):
            return []  # empty, or caught mid-sync: wait for content
        if len(lines) < self.count or _digest(lines[:self.count]) != self.digest:
            print(f"{self.path.name} was rewritten, not appended to: its current lines count as handled",
                  file=self.log, flush=True)
            self._save(lines)
            return []
        new = [line.strip() for line in lines[self.count:] if line.strip()]
        self._save(lines)
        return new


class Outbox:
    """답.txt: the latest answers, newest last, each under '> request'."""

    def __init__(self, path, keep=KEEP_ANSWERS):
        self.path, self.keep = Path(path), keep
        self.blocks, self.lock = [], threading.Lock()

    def add(self, request, answer):
        with self.lock:
            self.blocks = (self.blocks + [f"> {request}\n{answer}"])[-self.keep:]
            pr.write_if_changed(self.path, "\n".join(self.blocks) + "\n")


class Hub:
    def __init__(self, cache_dir, drive_dir, state_dir, askers=None, log=None):
        self.cache, self.drive, state = Path(cache_dir), Path(drive_dir), Path(state_dir)
        self.log = log or sys.stderr
        self.feed = pr.Feed(self.cache, self.drive)
        self.queue = router.ActionQueue(state / "actions.jsonl")
        self.inbox = Inbox(self.drive / INBOX, state / "inbox.json", self.log)
        self.outbox = Outbox(self.drive / OUTBOX)
        self.askers = askers
        self.pool = ThreadPoolExecutor(max_workers=4)
        self._lock = threading.Lock()  # one request routed at a time: action ids never collide
        self._tasks_version, self._problems = None, None

    def handle(self, request, reply_to, now=None):
        """Answer one request. reply_to(answer) is called once; for AI questions, later, from a worker."""
        with self._lock:
            reply = router.route(request, self.cache, self.queue, now)
        if reply.kind != "ask":
            reply_to(reply.text)
        elif not self.askers:
            reply_to("AI 연결 안 됨")
        else:
            self.pool.submit(self._ask_ai, request, reply_to)
        return reply

    def _ask_ai(self, question, reply_to):
        """The fastest AI's first useful line goes out: one line for Pickle, as early as possible."""
        block = ai_board.parse(ai_board.post(question, datetime.now()))[-1]
        sent, lock = [], threading.Lock()

        def first(slot, line):
            with lock:
                if not sent and not ai_board.banned_in(line):
                    sent.append(line)
                    reply_to(line)

        ai_board.fill(block, self.askers, on_line=first)
        if not sent:
            reply_to("AI 답 없음")

    def tick(self, now=None):
        """One pass: refresh answer files, answer new requests, refresh 작업.txt. Well under 1 ms idle."""
        now = now or datetime.now()
        _, problems = self.feed.step(now)
        if problems != self._problems:
            for problem in problems:
                print(f"  {problem}", file=self.log, flush=True)
            self._problems = problems
        for request in self.inbox.poll():
            self.handle(request, lambda answer, request=request: self.outbox.add(request, answer), now)
        self.queue.refresh()
        if self.queue.version != self._tasks_version:
            lines = self.queue.view()
            pr.write_if_changed(self.drive / TASKS, "\n".join(lines) + "\n" if lines else "없음\n")
            self._tasks_version = self.queue.version

    def console(self, inp=None, out=None):
        """Requests typed into the hub's own window get the same answers, printed right there."""
        inp, out, lock = inp or sys.stdin, out or sys.stdout, threading.Lock()

        def say(answer):
            with lock:
                print(answer, file=out, flush=True)

        for line in inp:
            if line.strip():
                self.handle(line.strip(), say)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--drive", required=True, help="the Drive folder Pickle reads (synced by Google Drive for desktop)")
    p.add_argument("--cache", default="downloads", help="cache directory (default: downloads)")
    p.add_argument("--state", help="action log and inbox position (default: <cache>/.hub)")
    p.add_argument("--interval", type=float, default=0.05, help="seconds between checks (default 0.05)")
    p.add_argument("--ai", action="store_true", help="answer free questions with Claude and GPT (needs API keys)")
    args = p.parse_args(argv)

    askers = None
    if args.ai:
        askers, warmers = ai_board.load_ais()
        ai_board.warm_all(warmers)
    hub = Hub(args.cache, args.drive, args.state or Path(args.cache) / ".hub", askers)
    threading.Thread(target=hub.console, daemon=True).start()
    print(f"hub ready: {args.drive} (requests can be typed here too; Ctrl+C stops)", file=sys.stderr, flush=True)
    try:
        while True:
            hub.tick()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
