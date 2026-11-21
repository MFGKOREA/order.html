#!/usr/bin/env python3
"""Pickle's hub: one resident process on the store PC that keeps every answer ready.

Files in the Drive folder Pickle reads (--drive):
  재고.txt 매출.txt 입고.txt BOH.txt   ready-made answers, rewritten when the cache changes
  재고_ㄱ.txt …  입고_오늘/내일/모레.txt  the same answers in small slices (fewer tokens per read)
  작업.txt                            pending actions + the 3 latest finished; 레미 does the 접수 lines
  요청.txt                            requests, one per line, appended by Pickle (or anyone)
  답.txt                              the latest answer, under "> request"
  허브상태.txt                        '허브 정상 <time>' + today's AI spend, every minute
  노무.txt                            daily labor check: 52h, 미태그, 스케줄 없이 출근, 월 마감 (tools/labor.py)
  게시판.txt                          the team's log: status tags, missing or late AIs, code (Pickle never reads it)
  대화.txt                            the shared ledger and handoff file: one line per handoff, every AI appends

Everything written there passes the personal-information filter first (tools/privacy.py; extra
private words go in <state>/private_terms.txt). Requests can also be typed into the hub's window.

Usage: python3 tools/hub.py --drive "<Drive folder Pickle reads>" [--ai]
       python3 tools/hub.py --drive "<…>" --board   (게시판 확인 once; also "게시판 확인" typed in the window)
--ai uses whichever of ANTHROPIC_API_KEY / OPENAI_API_KEY is set; with only OpenAI, GPT does Claude's part.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ai_board  # noqa: E402
import eventlog  # noqa: E402
import hub_page  # noqa: E402
import labor  # noqa: E402
import meter  # noqa: E402
import pickle_relay as pr  # noqa: E402
import pipeline  # noqa: E402
import privacy  # noqa: E402
import retryq  # noqa: E402
import router  # noqa: E402
import hubkeys  # noqa: E402
import sources  # noqa: E402

INBOX, OUTBOX, TASKS, BOARD, LEDGER = "요청.txt", "답.txt", "작업.txt", "게시판.txt", "대화.txt"
HEALTH = "허브상태.txt"  # rewritten every HEARTBEAT seconds; an old time there means the hub is off
HEARTBEAT = 60
LABOR = "노무.txt"  # daily labor check (tools/labor.py), every HEARTBEAT seconds
SYNC_SECONDS = 300  # data sources (tools/sources.py) refresh, in the background
OPEN_RE = re.compile(r"^## \[대기\] (Q-\d{8}-\d{3}) \d{1,2}:\d{2} (.+?) → (.+)$")
DONE_RE = re.compile(r"\[완료\] (Q-\d{8}-\d{3})")
SLOT_PROVIDER = {"GPT": "openai", "Claude": "anthropic"}
KEEP_ANSWERS = 1  # 답.txt holds only the latest answer, so Pickle reads the fewest tokens
# One line any AI can append. Statuses: who is waiting, who is checking, who must confirm.
HANDOFF_STATUSES = ("대기", "처리중", "검증중", "확인대기", "접수", "완료", "반려", "한도")
RULE_SOURCE = {  # rule answers never call an AI; the ledger still names the file the number came from
    "inventory": ("재고", "앱"), "inbound": ("입고", "앱"), "sales": ("매출", "앱"),
    "promotions": ("행사", "앱"), "boh": ("출퇴근", "HR"), "roster": ("근무표", "HR"), "multi": ("자료", "앱"),
}
TASK_ID_RE = re.compile(r"#(\d+)")
STATUS_WORD_RE = re.compile(r"#(\d+)\s+(접수|완료|실패)")


def format_handoff(rid, frm, to, status, body):
    """One ledger line: id | from | to | status | body. Body is one line, no greeting."""
    body = " ".join((body or "").split())
    return f"{rid} | {frm} | {to} | {status} | {body}"


def parse_handoff(line):
    """The same line back into a dict, or None when it is not a handoff."""
    parts = [part.strip() for part in (line or "").split("|", 4)]
    if len(parts) != 5 or not parts[0] or parts[3] not in HANDOFF_STATUSES:
        return None
    return {"id": parts[0], "from": parts[1], "to": parts[2], "status": parts[3], "body": parts[4]}


def arrow_result(text):
    """결론 / 근거 / 확인 필요 as one line joined by arrows. '' when it is not that shape."""
    parsed = pipeline.parse_answer(text or "")
    if not parsed:
        return ""
    return f"결론: {parsed['결론']} → 근거: {parsed['근거']} → 확인 필요: {parsed['확인 필요']}"


def open_remy_questions(board_text):
    """(qid, question) for each '→ 레미' question on the board that has no [완료] line yet."""
    asked, done = [], set(DONE_RE.findall(board_text))
    for line in board_text.splitlines():
        m = OPEN_RE.match(line.strip())
        if m and "레미" in m[3] and m[1] not in done and m[1] not in (q for q, _ in asked):
            asked.append((m[1], m[2]))
    return asked


def answer_board(drive, cache, ask, now=None, system=None):
    """게시판 확인 (prompts/remy.txt): answer each open '→ 레미' question with `ask` (GPT) from the
    cached data, and append one 'Q번호 답: 결론: … / 근거: … / 확인 필요: …' line per question to
    요청.txt, where the hub checks and delivers it. Returns the lines written."""
    drive, now = Path(drive), now or datetime.now()
    try:
        board = (drive / BOARD).read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return []
    system = system or pipeline.load_prompt("gpt")
    out = []
    for qid, question in open_remy_questions(board):
        data = pipeline.gather(question, cache, now)
        env = pipeline.envelope(qid, question, ["레미"], data, now, requester="게시판")
        parsed = pipeline.parse_answer("\n".join(ask(json.dumps(env, ensure_ascii=False), system)))
        if not parsed:
            continue
        check = parsed["확인 필요"]
        check = "레미 화면 확인 전 자료 기준 답" + ("" if check in ("", "없음") else f"; {check}")
        out.append(f"{qid} 답: 결론: {parsed['결론']} / 근거: {parsed['근거']} / 확인 필요: {check}")
    if out:
        with (drive / INBOX).open("a", encoding="utf-8") as f:
            f.write("".join(line + "\n" for line in out))
    return out


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


class Ledger:
    """대화.txt is the human mirror. The store is SQLite (WAL), one writer, idempotent lines."""

    def __init__(self, path, state_path, scrub=None, alert=None, log=None, secrets=()):
        self.path, self.scrub, self.alert = Path(path), scrub, alert
        self.secrets, self.mem = list(secrets), {}
        self.events = eventlog.EventLog(state_path, self.path)  # migrates an existing 대화.txt

    def add(self, rid, frm, to, status, body):
        line = hubkeys.redact(format_handoff(rid, frm, to, status, body), self.secrets)
        if self.scrub:
            line, hits = self.scrub(line)
            if hits and self.alert:
                self.alert(f"개인정보 가림 대화.txt: {', '.join(hits)}")
        rec = parse_handoff(line)
        if not rec:
            return False
        return self.events.add(line, rec)

    def poll(self):
        """Lines another AI appended to 대화.txt. Stored once, then handed back."""
        return [rec for rec in (parse_handoff(line) for line in self.events.poll_new()) if rec]

    def next_rule_id(self, now):
        """R-YYYYMMDD-NNN for an answer the rules wrote (no Q-id, no AI)."""
        return self.events.next_rule_id(now)

    def recent(self, n=12):
        return self.events.recent(n)

    def record_rule(self, reply, now, requester):
        """A request the rules finished: data, a held order, or 확인 #번호. No AI call."""
        kind, text = reply.kind, reply.text or ""
        if kind in ("order", "hr_confirm"):
            for line in text.splitlines() or [text]:
                found = TASK_ID_RE.search(line)
                status = "확인대기" if "확인대기" in line else "접수"
                self.add(f"#{found[1]}" if found else self.next_rule_id(now), requester, "레미", status, line)
            return
        if kind == "status":
            found = STATUS_WORD_RE.match(text)
            if not found:
                self.add(self.next_rule_id(now), "허브", requester, "완료",
                         f"결론: {text} → 근거: 규칙, 자료 없음 → 확인 필요: 없음")
                return
            if found[2] == "접수":
                self.add(f"#{found[1]}", requester, "레미", "접수", text)
            else:
                self.add(f"#{found[1]}", "레미", "피클", "완료", text)
            return
        label = RULE_SOURCE.get(kind)
        flat = " / ".join(line.strip() for line in text.splitlines() if line.strip())
        if label:
            name, source = label
            body = f"결론: {flat} → 근거: {name} ({source} {now.month}/{now.day} {now:%H:%M}) → 확인 필요: 없음"
        else:
            body = f"결론: {flat} → 근거: 규칙, 자료 없음 → 확인 필요: 없음"
        self.add(self.next_rule_id(now), "허브", requester, "완료", body)

    def from_pipeline(self, qid, state, fields):
        """One ledger line per status the pipeline already tracks. Remember from/to across the states."""
        mem = self.mem.setdefault(qid, {})
        if fields.get("요청자"):
            mem["from"] = fields["요청자"]
        if "대상" in fields:
            mem["to"] = list(fields["대상"])
        if fields.get("질문"):
            mem["task"] = fields["질문"]
        frm = mem.get("from") or "피클"
        targets = mem.get("to") or []
        to = ",".join(targets)
        task = mem.get("task") or ""
        if state == "대기":
            self.add(qid, frm, to or "허브", "대기" if to else "한도", task)
        elif state == "처리중":
            self.add(qid, "허브", to or "허브", "처리중", task)
        elif state == "검증중":
            lead = fields.get("lead") or (targets[0] if targets else "Claude")
            body = arrow_result(fields.get("review") or "") or task
            self.add(qid, lead, fields.get("checker") or "GPT", "검증중", body)
        elif state == "완료":
            answer = fields.get("answer") or ""
            if answer == pipeline.LIMIT:
                self.add(qid, "허브", frm, "한도", answer)
                return
            who = "캐시" if fields.get("cached") else ((fields.get("answered") or [None])[0] or "허브")
            self.add(qid, who, frm, "완료", arrow_result(answer) or answer)


class Hub:
    def __init__(self, cache_dir, drive_dir, state_dir, askers=None, log=None, deadline=pipeline.DEADLINE,
                 confirm=None, env=None):
        self.cache, self.drive, self.state = Path(cache_dir), Path(drive_dir), Path(state_dir)
        self.log = log or sys.stderr
        self.filter = privacy.Filter(self.state / "private_terms.txt")
        self.feed = pr.Feed(self.cache, self.drive, scrub=self.filter.scrub)
        if confirm is None:  # 발주·HR 확정 wait for "확인 #번호" unless HUB_CONFIRM=0
            confirm = os.environ.get("HUB_CONFIRM", "1") != "0"
        self.queue = router.ActionQueue(self.state / "actions.jsonl", confirm=confirm)
        self.env = os.environ if env is None else env
        self.inbox = Inbox(self.drive / INBOX, self.state / "inbox.json", self.log)
        self.outbox = Outbox(self.drive / OUTBOX, scrub=self.filter.scrub, alert=self.alert)
        self.board = pipeline.Board(self.drive / BOARD, scrub=self.filter.scrub, alert=self.alert)
        self.meter = meter.Meter(self.state / "usage.jsonl", alert=self.alert)
        self.ledger = Ledger(self.drive / LEDGER, self.state / "ledger.sqlite", scrub=self.filter.scrub,
                             alert=self.alert, log=self.log, secrets=hubkeys.secret_values(self.env))
        self.retry = retryq.RetryQueue(self.state / "retry.sqlite")
        self.page_port = None
        self._now = None
        self.log_book = pipeline.Log(self.state / "envelopes.jsonl")  # every request; restarts, weekly summary
        self.pipeline = pipeline.Pipeline(
            self.cache, askers, board=self.board, deadline=deadline, log=self.log_book,
            reply_for=lambda request: (lambda answer: self.outbox.add(request, answer)),
            blocked=lambda slot: self.meter.blocked(SLOT_PROVIDER.get(slot)),
            on_status=self.ledger.from_pipeline)
        self.pool = ThreadPoolExecutor(max_workers=4)
        self._lock = threading.Lock()  # one request routed at a time: action ids never collide
        self._tasks_version, self._problems, self._week_checked = None, None, None
        self._beat, self._synced, self.sync_thread, self._sync_problems = None, None, None, []
        self.labor_alerted = labor.Alerted(self.state / "labor_alerted.json")

    def alert(self, message):
        """Tell 신우님: the hub's window and <state>/alerts.log (never the Drive folder)."""
        message = hubkeys.redact(message, hubkeys.secret_values(self.env))
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
        start = time.perf_counter()
        with self._lock:
            reply = router.route(request, self.cache, self.queue, now)
        if reply.kind not in ("ask", "status"):  # free questions are logged by the pipeline
            self.log_book.write({"at": (now or datetime.now()).isoformat(timespec="seconds"), "상태": "완료",
                                 "route": "hub", "kind": reply.kind, "요청자": requester,
                                 "seconds": round(time.perf_counter() - start, 4)})
        if reply.kind != "ask":  # rules answered it: the ledger records the handoff, no model call
            self.ledger.record_rule(reply, now or datetime.now(), requester)
        if reply.kind in quiet:
            pass
        elif reply.kind != "ask":
            reply_to(reply.text)
        else:
            self.pool.submit(self._run_request, request, reply_to, requester, None, None)
        return reply.kind

    def tick(self, now=None):
        """One pass: refresh answer files, answer new requests, refresh 작업.txt. Well under 1 ms idle."""
        now = now or datetime.now()
        self._now = now
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
        for rec in self.ledger.poll():
            self._take(rec)
        for job in self.retry.claim(now):
            self.pool.submit(self._replay, job)
        self.queue.refresh()
        if self.queue.version != self._tasks_version:
            lines = self.queue.view()
            text, hits = self.filter.scrub("\n".join(lines) + "\n" if lines else "없음\n")
            if hits:
                self.alert(f"개인정보 가림 작업.txt: {', '.join(hits)}")
            pr.write_if_changed(self.drive / TASKS, text)
            self._tasks_version = self.queue.version
        self.weekly(now)
        self.refresh_sources(now)
        self.heartbeat(now)

    def _take(self, rec):
        """A line another AI appended. 완료 to 피클 closes a waiting question. 대기 to Claude or GPT is their task."""
        if rec["status"] == "완료" and rec["to"] in ("피클", "허브") and re.fullmatch(r"Q-\d{8}-\d{3}", rec["id"]):
            self.pipeline.accept_remy(rec["id"], rec["body"].replace(" → ", " / "))
            return
        if rec["status"] == "대기" and rec["to"] in ("Claude", "GPT"):
            self.pool.submit(self._run_named, rec)

    def _job_key(self, request, requester, force):
        return eventlog.line_key(f"{requester}|{force or ''}|{request}")

    def _needs_retry(self, record):
        """A finished AI call that produced no answer. Budget stops and 레미 waits are not retries."""
        if not record or record.get("cached"):
            return False
        if record.get("answer") != pipeline.UNKNOWN:
            return False
        return any(name in (record.get("targets") or []) for name in ("Claude", "GPT"))

    def _run_request(self, request, reply, requester, force, job_key):
        self._now = self._now or datetime.now()
        err = None
        record = None
        try:
            if force:
                record = self.pipeline.run(request, reply, requester, force=force)
            else:
                record = self.pipeline.run(request, reply, requester)
        except Exception as exc:  # the queue, not the caller, decides whether this runs again
            err = type(exc).__name__
        if job_key:
            if err or self._needs_retry(record):
                if self.retry.fail(job_key, err or "답 없음", self._now) == "dead":
                    self._bury(request, requester, force, err or "답 없음")
            else:
                self.retry.succeed(job_key)
        elif err or self._needs_retry(record):
            self.retry.note(self._job_key(request, requester, force),
                            {"request": request, "requester": requester, "force": force},
                            err or "답 없음", self._now)

    def _replay(self, job):
        payload = job["payload"]

        def reply(answer, request=payload["request"]):
            self.outbox.add(request, answer)

        self._run_request(payload["request"], reply, payload["requester"], payload.get("force"), job["key"])

    def _bury(self, request, requester, force, error):
        self.ledger.add("재시도", requester or "허브", force or "GPT", "반려",
                        f"결론: 재시도 끝 → 근거: {error} → 확인 필요: 신우님 확인")

    def _run_named(self, rec):
        """The handoff named the AI. Code Claude writes is still checked by GPT; the budget cap still applies."""
        def reply(answer, request=rec["body"]):
            self.outbox.add(request, answer)

        self._run_request(rec["body"], reply, rec["from"], rec["to"], None)

    def request_confirm(self, task_id):
        """Append `확인 #id` when that action is still 확인대기. One tap on the hub screen."""
        try:
            task_id = int(task_id)
        except (TypeError, ValueError):
            return False
        if not any(line.startswith(f"#{task_id} 확인대기") for line in self.queue.view()):
            return False
        with (self.drive / INBOX).open("a", encoding="utf-8") as handle:
            handle.write(f"확인 #{task_id}\n")
        return True

    def screen(self):
        """What the hub page shows. Badges are 정상, 지연, or 끊김. No invented numbers."""
        askers = self.pipeline.askers or {}

        def ai(name, provider):
            if name not in askers or self.meter.blocked(provider):
                return "끊김"
            if self.retry.open_count():
                return "지연"
            return "정상"

        remy = "지연" if self.ledger.events.open_to("레미") else "정상"
        badges = [("Claude", ai("Claude", "anthropic")), ("GPT", ai("GPT", "openai")), ("레미", remy), ("피클", "정상")]
        confirms = []
        for line in self.queue.view():
            parts = line.split(" ", 3)
            if len(parts) >= 4 and parts[1] == "확인대기":
                confirms.append({"id": parts[0][1:], "text": parts[3]})
        return {"badges": badges, "confirms": confirms, "timeline": self.ledger.recent(),
                "spend": self.meter.status_line((self._now or datetime.now()).date())}

    def sync(self, now):
        return sources.sync(self.cache, now, self.env)

    def refresh_sources(self, now):
        """Every SYNC_SECONDS, pull the order app and the HR board into the cache, on a thread so the
        tick never waits on the network. Nothing happens when neither source is set."""
        if not (self.env.get("ORDER_APP_API") or self.env.get("HR_BOARD_PASSWORD")):
            return
        if self.sync_thread and self.sync_thread.is_alive():
            return
        if self._synced and (now - self._synced).total_seconds() < SYNC_SECONDS:
            return
        self._synced = now

        def run():
            _, problems = self.sync(now)
            for problem in problems:
                if problem not in self._sync_problems:
                    self.alert(problem)
            self._sync_problems = problems

        self.sync_thread = threading.Thread(target=run, daemon=True)
        self.sync_thread.start()

    def heartbeat(self, now):
        """허브상태.txt: when the hub last ran and today's AI spend, so a stopped hub shows (Pickle
        answers "허브 꺼짐" when the time there is more than a few minutes old)."""
        if self._beat and (now - self._beat).total_seconds() < HEARTBEAT:
            return
        self._beat = now
        text = f"허브 정상 {now:%Y-%m-%d %H:%M}\n{self.meter.status_line(now.date())}\n"
        for name, state in self.screen()["badges"]:
            text += f"{name} {state}\n"
        if self.page_port:
            text += f"화면 http://127.0.0.1:{self.page_port}\n"
        if self._sync_problems:
            text += "\n".join(self._sync_problems) + "\n"
        pr.write_if_changed(self.drive / HEALTH, self.filter.scrub(text)[0])
        report, alerts = labor.report(self.cache, now)
        pr.write_if_changed(self.drive / LABOR, self.filter.scrub(report)[0])
        for message in self.labor_alerted.new(alerts):
            self.alert(f"[노무] {message}")
            self.board.note(f"[노무] {message}")

    def weekly(self, now):
        """On the first check of a new week, post last week's summary on the board (once)."""
        today = now.date()
        if self._week_checked == today:
            return
        self._week_checked = today
        last_monday = today - timedelta(days=today.weekday() + 7)
        path = self.state / "weekly.json"
        try:
            last = json.loads(path.read_text(encoding="utf-8"))["last"]
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            last = None
        if last != last_monday.isoformat():
            if last is not None:  # the very first run starts counting; there is no week to report yet
                self.board.note(meter.weekly_summary(self.log_book.read(), self.meter.records, last_monday))
            self.state.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"last": last_monday.isoformat()}), encoding="utf-8")

    def console(self, inp=None, out=None):
        """Requests typed into the hub's own window get the same answers, printed right there."""
        inp, out, lock = inp or sys.stdin, out or sys.stdout, threading.Lock()

        def say(answer):
            with lock:
                print(answer, file=out, flush=True)

        for line in inp:
            if line.strip() == "게시판 확인" and "GPT" in (self.pipeline.askers or {}):
                for written in answer_board(self.drive, self.cache, self.pipeline.askers["GPT"]):
                    say(written)
            elif line.strip():
                self.handle(line.strip(), say, requester="신우님")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--drive", help="the Drive folder Pickle reads (synced by Google Drive for desktop)")
    p.add_argument("--cache", default="downloads", help="cache directory (default: downloads)")
    p.add_argument("--state", help="logs, alerts, spend, private words (default: <cache>/.hub)")
    p.add_argument("--interval", type=float, default=0.05, help="seconds between checks (default 0.05)")
    p.add_argument("--ai", action="store_true", help="answer free questions with Claude and GPT (needs API keys)")
    p.add_argument("--board", action="store_true",
                   help="게시판 확인 once: GPT answers open '→ 레미' questions into 요청.txt, then exit")
    p.add_argument("--weekly", action="store_true", help="print this week's summary so far and exit")
    args = p.parse_args(argv)
    state = Path(args.state or Path(args.cache) / ".hub")

    if args.weekly:
        today = datetime.now().date()
        print(meter.weekly_summary(pipeline.Log(state / "envelopes.jsonl").read(),
                                   meter.Meter(state / "usage.jsonl").records, today - timedelta(days=today.weekday())))
        return 0
    if not args.drive:
        p.error("--drive is required")

    if args.board:
        import ask_gpt
        m = meter.Meter(state / "usage.jsonl")
        if m.blocked("openai"):
            print("AI 오늘 한도 도달", file=sys.stderr)
            return 1
        ask_gpt.on_usage = lambda model, i, o: m.record("openai", model, i, o)
        for line in answer_board(args.drive, args.cache, ask_gpt.lines):
            print(line)
        return 0

    askers = None
    if args.ai:
        askers, warmers = ai_board.load_ais()
        ai_board.warm_all(warmers)
    hub = Hub(args.cache, args.drive, state, askers)
    if args.ai:
        if "GPT" in askers:
            import ask_gpt
            ask_gpt.on_usage = lambda model, i, o: hub.meter.record("openai", model, i, o)
        if "Claude" in askers:
            import ask_claude
            ask_claude.on_usage = lambda model, i, o: hub.meter.record("anthropic", model, i, o)
        else:
            print("Claude: ANTHROPIC_API_KEY 없음, 건너뜀 (GPT가 대신 답함)", file=sys.stderr, flush=True)
    threading.Thread(target=hub.console, daemon=True).start()
    host = os.environ.get("HUB_HOST", "127.0.0.1")
    port = int(os.environ.get("HUB_PORT", "8765"))
    if hub_page.serve(lambda: hub_page.render(hub.screen()), hub.request_confirm, host, port):
        hub.page_port = port
        print(f"screen: http://{host}:{port}", file=sys.stderr, flush=True)
    print(f"hub ready: {args.drive} (requests can be typed here too; Ctrl+C stops)", file=sys.stderr, flush=True)
    try:
        while True:
            hub.tick()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
