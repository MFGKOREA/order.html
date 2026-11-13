#!/usr/bin/env python3
"""Pickle's hub: one resident process on the store PC that keeps every answer ready.

Files in the Drive folder Pickle reads (--drive):
  재고.txt 매출.txt 입고.txt BOH.txt   ready-made answers, rewritten when the cache changes
  재고_ㄱ.txt …  입고_오늘/내일/모레.txt  the same answers in small slices (fewer tokens per read)
  작업.txt                            pending actions + the 3 latest finished; 레미 does the 접수 lines
  요청.txt                            requests, one per line, appended by Pickle (or anyone)
  답.txt                              the latest answer, under "> request"
  게시판.txt                          the team's log: status tags, missing or late AIs, code (Pickle never reads it)

Everything written there passes the personal-information filter first (tools/privacy.py; extra
private words go in <state>/private_terms.txt). Requests can also be typed into the hub's window.

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
import pipeline  # noqa: E402
import privacy  # noqa: E402
import router  # noqa: E402

INBOX, OUTBOX, TASKS, BOARD = "요청.txt", "답.txt", "작업.txt", "게시판.txt"
KEEP_ANSWERS = 1  # 답.txt holds only the latest answer, so Pickle reads the fewest tokens


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
    """답.txt: the latest answer under '> request', with personal information masked."""

    def __init__(self, path, keep=KEEP_ANSWERS, scrub=None, alert=None):
        self.path, self.keep, self.scrub, self.alert = Path(path), keep, scrub, alert
        self.blocks, self.lock = [], threading.Lock()

    def add(self, request, answer):
        if self.scrub:
            answer, hits = self.scrub(answer)
            if hits and self.alert:
                self.alert(f"개인정보 가림 답.txt: {', '.join(hits)}")
        with self.lock:
            self.blocks = (self.blocks + [f"> {request}\n{answer}"])[-self.keep:]
            pr.write_if_changed(self.path, "\n".join(self.blocks) + "\n")


class Hub:
    def __init__(self, cache_dir, drive_dir, state_dir, askers=None, log=None, deadline=pipeline.DEADLINE):
        self.cache, self.drive, self.state = Path(cache_dir), Path(drive_dir), Path(state_dir)
        self.log = log or sys.stderr
        self.filter = privacy.Filter(self.state / "private_terms.txt")
        self.feed = pr.Feed(self.cache, self.drive, scrub=self.filter.scrub)
        self.queue = router.ActionQueue(self.state / "actions.jsonl")
        self.inbox = Inbox(self.drive / INBOX, self.state / "inbox.json", self.log)
        self.outbox = Outbox(self.drive / OUTBOX, scrub=self.filter.scrub, alert=self.alert)
        self.board = pipeline.Board(self.drive / BOARD, scrub=self.filter.scrub, alert=self.alert)
        self.pipeline = pipeline.Pipeline(
            self.cache, askers, board=self.board, deadline=deadline,
            log=pipeline.Log(self.state / "envelopes.jsonl"),  # status changes; restarts and weekly summary
            reply_for=lambda request: (lambda answer: self.outbox.add(request, answer)))
        self.pool = ThreadPoolExecutor(max_workers=4)
        self._lock = threading.Lock()  # one request routed at a time: action ids never collide
        self._tasks_version, self._problems = None, None

    def alert(self, message):
        """Tell 신우님: the hub's window and <state>/alerts.log (never the Drive folder)."""
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}"
        print(line, file=self.log, flush=True)
        self.state.mkdir(parents=True, exist_ok=True)
        with (self.state / "alerts.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def handle(self, request, reply_to, now=None, quiet=(), requester="피클"):
        """Answer one request. reply_to(answer) is called once (free questions later, from a
        worker; 레미's questions when 레미 answers), except for reply kinds listed in `quiet`."""
        m = pipeline.REMY_RE.match(request)
        if m:
            status = self.pipeline.accept_remy(m[1], m[2])
            if "remy_answer" not in quiet:
                reply_to(status)
            return "remy_answer"
        with self._lock:
            reply = router.route(request, self.cache, self.queue, now)
        if reply.kind in quiet:
            pass
        elif reply.kind != "ask":
            reply_to(reply.text)
        else:
            self.pool.submit(self.pipeline.run, request, reply_to, requester)
        return reply.kind

    def tick(self, now=None):
        """One pass: refresh answer files, answer new requests, refresh 작업.txt. Well under 1 ms idle."""
        now = now or datetime.now()
        _, problems = self.feed.step(now)
        if problems != self._problems:
            for problem in problems:
                if problem.startswith("개인정보 가림") and problem not in (self._problems or ()):
                    self.alert(problem)
                else:
                    print(f"  {problem}", file=self.log, flush=True)
            self._problems = problems
        for request in self.inbox.poll():
            # Status lines ("#3 완료") and 레미's answers show in 작업.txt and 게시판.txt; they are
            # kept out of 답.txt so they never replace Pickle's answer.
            self.handle(request, lambda answer, request=request: self.outbox.add(request, answer), now,
                        quiet=("status", "remy_answer"))
        self.queue.refresh()
        if self.queue.version != self._tasks_version:
            lines = self.queue.view()
            text, hits = self.filter.scrub("\n".join(lines) + "\n" if lines else "없음\n")
            if hits:
                self.alert(f"개인정보 가림 작업.txt: {', '.join(hits)}")
            pr.write_if_changed(self.drive / TASKS, text)
            self._tasks_version = self.queue.version

    def console(self, inp=None, out=None):
        """Requests typed into the hub's own window get the same answers, printed right there."""
        inp, out, lock = inp or sys.stdin, out or sys.stdout, threading.Lock()

        def say(answer):
            with lock:
                print(answer, file=out, flush=True)

        for line in inp:
            if line.strip():
                self.handle(line.strip(), say, requester="신우님")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--drive", required=True, help="the Drive folder Pickle reads (synced by Google Drive for desktop)")
    p.add_argument("--cache", default="downloads", help="cache directory (default: downloads)")
    p.add_argument("--state", help="action log, inbox position, alerts, private words (default: <cache>/.hub)")
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
