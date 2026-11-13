"""AI answers for Pickle: one free question in, one finished 3-line answer out.

- The question goes only to the AI that owns its kind: code, automation and documents go to
  Claude and then GPT checks them; analysis goes to Claude; checking and everything else go to
  GPT; "[중요]" asks Claude and GPT at once; browser work goes to 레미, who answers later
  through 요청.txt ("Q-…-007 답: 결론: … / 근거: … / 확인 필요: …").
- The AIs get the question in an envelope (prompts/claude.txt, prompts/gpt.txt) with the cache
  lines it touches as 자료, each tagged (출처 시각).
- Every answer must be 결론 / 근거 / 확인 필요, with (출처 시각) in 근거 whenever it states a
  number or a staff name. An answer that breaks this is sent back once, then dropped.
- The AIs get DEADLINE seconds. A missing AI is noted on the board and the rest carry on; a late
  answer goes to the board, and Pickle's answer is redone only when the late one disagrees.
- When two answers state different numbers or names, both go under 확인 필요.
"""
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pickle_relay as pr  # noqa: E402
import router  # noqa: E402

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
DEADLINE = 10.0  # seconds: the "2중 전달 10초" standard
SOURCES = ("HR", "세콤", "웹", "POS", "매장")
LABELS = ("결론", "근거", "확인 필요")
# Analysis answers may use their three labels; everything else banned for Pickle stays banned.
ANALYSIS_BANNED = tuple(w for w in pr.BANNED if w not in ("결론", "근거", "확인필요", "확인 필요"))
UNKNOWN = "결론: 모름\n근거: 출처가 있는 답 없음\n확인 필요: 신우님 확인"
NO_AI = "AI 연결 안 됨"

CATEGORY_WORDS = (  # first match wins; compared without spaces, lower case
    ("browser", ("세콤", "hr", "사이트", "로그인", "화면", "스크래핑", "크롤링", "홈페이지", "브라우저", "웹페이지")),
    ("build", ("코드", "스크립트", "자동화", "함수", "엑셀", "수식", "매크로", "버그", "에러", "오류", "프로그램",
               "파이썬", "python", "javascript", "자바스크립트", "api", "sql", "작성", "초안", "공지문", "보고서",
               "문서", "만들어")),
    ("verify", ("검증", "검토", "맞아", "맞는지", "맞나", "틀린", "틀렸", "체크해", "리뷰")),
    ("analysis", ("분석", "예측", "추천", "발주량", "얼마나", "원인", "비교", "추세", "전략", "개선")),
)
IMPORTANT_RE = re.compile(r"^\s*\[중요\]\s*")
LABEL_RE = re.compile(r"^\s*[-*]*\s*\**\s*(결론|근거|확인\s?필요)\s*\**\s*[:：]\s*(.*)$")
FENCE_RE = re.compile(r"```.*?```", re.S)
PAREN_RE = re.compile(r"\(([^()]*)\)")
TIME_RE = re.compile(r"\d{1,2}:\d{2}|\d{1,2}/\d{1,2}")
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
REMY_RE = re.compile(r"^\s*(Q-\d{8}-\d{3})\s*답\s*[:：]\s*(.+)$")
REMY_SPLIT_RE = re.compile(r"\s*/\s*(?=(?:결론|근거|확인\s?필요)\s*[:：])")


def load_prompt(name):
    return (PROMPTS / f"{name}.txt").read_text(encoding="utf-8")


def classify(question):
    """(kind, important): kind is browser, build, verify, analysis or general."""
    important = bool(IMPORTANT_RE.match(question))
    compact = re.sub(r"\s+", "", IMPORTANT_RE.sub("", question)).lower()
    for kind, words in CATEGORY_WORDS:
        if any(w in compact for w in words):
            return kind, important
    return "general", important


def plan(kind, important):
    """(answerers, checker) for a kind of question. Only [중요] calls both AIs."""
    if kind == "browser":
        return ["레미"], None
    if important:
        return ["Claude", "GPT"], None
    if kind == "build":
        return ["Claude"], "GPT"
    if kind == "analysis":
        return ["Claude"], None
    return ["GPT"], None  # verify, general


def _stamp(dt):
    return f"{dt.month}/{dt.day} {dt:%H:%M}"


def _file_stamp(cache_dir, key):
    try:
        return _stamp(datetime.fromtimestamp((Path(cache_dir) / pr.CACHE_FILES[key]).stat().st_mtime))
    except FileNotFoundError:
        return "?"


def gather(question, cache_dir, now):
    """Cache lines the question touches, each tagged (출처 시각): the envelope's 자료."""
    items = set(router.find_items(question, router.known_items(cache_dir)))
    compact = re.sub(r"\s+", "", question).lower()
    lines = []
    try:
        for i in pr.load(cache_dir, "inventory")["items"]:
            if i["name"] in items:
                lines.append(f"{pr.fmt_inventory(i, now)} (매장 {_stamp(datetime.fromisoformat(i['snapshot_at']))})")
    except router.DATA_ERRORS:
        pass
    try:
        today, when = now.date(), _file_stamp(cache_dir, "inbound")
        for (d, name), (q, u) in sorted(pr.inbound_totals(pr.load(cache_dir, "inbound")).items()):
            if name in items and d >= today:
                lines.append(f"{pr.fmt_inbound(name, d, q, u, today)} (매장 {when})")
    except router.DATA_ERRORS:
        pass
    if any(w in compact for w in router.TOPIC_WORDS["sales"]):
        try:
            lines.append(f"{pr.fmt_sales(pr.load(cache_dir, 'sales'))} (POS {_file_stamp(cache_dir, 'sales')})")
        except router.DATA_ERRORS:
            pass
    if any(w in compact for w in router.TOPIC_WORDS["boh"]):
        try:
            b = pr.load(cache_dir, "boh")
            lines.append(f"BOH: 근무 중 {b['on_duty']}명, 퇴근 완료 {b['off_duty']}명 "
                         f"(HR {now.month}/{now.day} {b['as_of']})")
        except router.DATA_ERRORS:
            pass
    return lines


def envelope(qid, question, targets, data_lines, now, requester="피클", status="처리중", review=None):
    """The one message format between the hub and Claude/GPT (DESIGN.md, 메시지 봉투)."""
    return {
        "id": qid, "날짜": now.date().isoformat(), "요청자": requester, "대상": list(targets),
        "질문": question, "원하는형식": "결론→근거→확인 필요",
        "출처": sorted({s for line in data_lines for s in SOURCES if f"({s} " in line}),
        "시각": now.strftime("%H:%M"), "상태": status, "자료": "\n".join(data_lines), "검토할답": review,
    }


def parse_answer(text):
    """{'결론', '근거', '확인 필요', 'code'} from a 3-line answer; None when there is no 결론."""
    code = "\n".join(FENCE_RE.findall(text or ""))
    parts, current = {}, None
    for line in FENCE_RE.sub("", text or "").splitlines():
        m = LABEL_RE.match(line)
        if m:
            current = "확인 필요" if m[1].startswith("확인") else m[1]
            parts[current] = m[2].strip()
        elif current and line.strip():
            parts[current] = f"{parts[current]} {line.strip()}".strip()
    if not parts.get("결론"):
        return None
    return {"결론": parts["결론"], "근거": parts.get("근거", ""), "확인 필요": parts.get("확인 필요") or "없음",
            "code": code}


def format_answer(p):
    return f"결론: {p['결론']}\n근거: {p['근거']}\n확인 필요: {p.get('확인 필요') or '없음'}"


def facts(text, names):
    """Numbers and known names in a piece of text."""
    return set(NUMBER_RE.findall(text)) | {n for n in names if n in text}


def source_of(p):
    """The (출처 시각) group in 근거, or ""."""
    for group in PAREN_RE.findall(p.get("근거", "")):
        if any(s in group for s in SOURCES) and TIME_RE.search(group):
            return f"({group})"
    return ""


def problem(parsed, staff=()):
    """Why an answer can't go out (None if it can): format, banned words, or a missing source."""
    if parsed is None:
        return "3줄 형식(결론/근거/확인 필요)이 아님"
    joined = " ".join(parsed[k] for k in LABELS)
    banned = [w for w in ANALYSIS_BANNED if w in joined]
    if banned:
        return f"금지어 {', '.join(banned)}"
    if facts(f"{parsed['결론']} {parsed['근거']}", staff) and not source_of(parsed):
        return "숫자·이름의 출처와 시각이 근거에 없음"
    return None


def compose(answers, names, notes=()):
    """One finished 3-line answer from the usable answers, lead first. Disagreements and notes go
    under 확인 필요."""
    if not answers:
        return UNKNOWN
    lead_slot, lead = answers[0]
    checks = [] if lead["확인 필요"] in ("", "없음") else [lead["확인 필요"]]
    for slot, other in answers[1:]:
        if facts(lead["결론"], names) != facts(other["결론"], names):
            checks.append(f"{lead_slot}: {lead['결론']} {source_of(lead)} / {slot}: {other['결론']} {source_of(other)}"
                          .replace("  ", " ").strip())
    checks += [n for n in notes if n]
    return format_answer({**lead, "확인 필요": "; ".join(checks) or "없음"})


def _collect(asker, message, system):
    return "\n".join(asker(message, system))


class Board:
    """게시판.txt in the Drive folder: an append-only log for the team. Pickle never reads it."""

    def __init__(self, path, scrub=None, alert=None):
        self.path, self.scrub, self.alert = Path(path), scrub, alert
        self.lock = threading.Lock()

    def note(self, text):
        if self.scrub:
            text, hits = self.scrub(text)
            if hits and self.alert:
                self.alert(f"게시판.txt: {', '.join(hits)}")
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            for attempt in range(20):
                try:
                    with self.path.open("a", encoding="utf-8") as f:
                        f.write(text.rstrip("\n") + "\n")
                    return
                except PermissionError:  # Windows: a sync client can hold the file for a moment
                    if attempt == 19:
                        raise
                    time.sleep(0.05)


def cache_key(question):
    """Same question, whatever the spacing, punctuation or [중요] mark."""
    return re.sub(r"[\s?!.,~…]+", "", IMPORTANT_RE.sub("", question)).lower()


class Log:
    """envelopes.jsonl in the hub's state folder: every status change of every question, with its
    result. Restarts and the weekly summary read it. Local only; never synced."""

    def __init__(self, path):
        self.path, self.lock = Path(path), threading.Lock()

    def write(self, record):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read(self):
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        records = []
        for line in lines:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:  # a line cut short by a crash: skip it
                pass
        return records


class Pipeline:
    def __init__(self, cache_dir, askers=None, systems=None, board=None, deadline=DEADLINE, clock=datetime.now,
                 log=None, reply_for=None, blocked=None):
        self.cache_dir, self.askers, self.board, self.log = cache_dir, askers or {}, board, log
        self.blocked = blocked or (lambda slot: False)  # slot -> True when its spending cap is reached
        self.systems = systems if systems is not None else {"Claude": load_prompt("claude"), "GPT": load_prompt("gpt")}
        self.deadline, self.clock = deadline, clock
        self.reply_for = reply_for  # question -> reply function, for 레미's questions after a restart
        self.pending = {}  # qid -> {"request", "reply"}: 레미's questions, answered later
        self.delivered = {}  # qid -> {"answers", "notes", "reply"}: for late answers
        self.late = {}  # qid -> [(slot, parsed)] that arrived after the deadline, before delivery
        self.cache = {}  # cache_key -> {"id", "date", "data", "answer"}: today's answers
        self.issues = {}  # qid -> {"missing": [...], "rejected": [...]}: for the log
        self._lock, self._count = threading.Lock(), {}
        self.pool = ThreadPoolExecutor(max_workers=8)
        self._restore()

    # -- small helpers -------------------------------------------------------------------------
    def note(self, text):
        if self.board:
            self.board.note(text)

    def status(self, qid, state, line=None, **fields):
        """A status change: one line on the board, one record in the log."""
        self.note(line or f"[{state}] {qid}")
        if self.log:
            self.log.write({"id": qid, "at": self.clock().isoformat(timespec="seconds"), "상태": state, **fields})

    def next_id(self, now):
        with self._lock:
            day = now.strftime("%Y%m%d")
            self._count[day] = self._count.get(day, 0) + 1
            return f"Q-{day}-{self._count[day]:03d}"

    def names(self):
        """(item names, staff names) in the cache: what counts as a name in an answer."""
        staff = set()
        try:
            staff = {e["name"] for e in pr.load(self.cache_dir, "boh").get("events", [])}
        except router.DATA_ERRORS:
            pass
        return router.known_items(self.cache_dir), staff

    def _issue(self, qid, kind, slot):
        with self._lock:
            self.issues.setdefault(qid, {"missing": [], "rejected": []})[kind].append(slot)

    def _restore(self):
        """After a restart: keep counting question numbers, keep today's cache, and keep waiting
        for 레미's open questions."""
        if not self.log:
            return
        today, waiting = self.clock().date().isoformat(), {}
        for r in self.log.read():
            qid = r.get("id", "")
            if re.fullmatch(r"Q-\d{8}-\d{3}", qid):
                self._count[qid[2:10]] = max(self._count.get(qid[2:10], 0), int(qid[11:]))
            if r.get("상태") == "대기" and r.get("대상") == ["레미"]:
                waiting[qid] = r
            elif r.get("상태") == "완료":
                waiting.pop(qid, None)
                if r.get("key") and r.get("date") == today and r.get("answer") not in (None, UNKNOWN, NO_AI):
                    self.cache[r["key"]] = {"id": qid, "date": today, "data": r.get("data", []), "answer": r["answer"]}
        if self.reply_for:
            for qid, r in waiting.items():
                self.pending[qid] = {"request": r["요청"], "reply": self.reply_for(r["요청"]), "key": r.get("key"),
                                     "data": r.get("data", [])}

    def _remember(self, qid, key, data, answer, now):
        if key and answer not in (UNKNOWN, NO_AI):
            with self._lock:
                self.cache[key] = {"id": qid, "date": now.date().isoformat(), "data": data, "answer": answer}

    # -- asking ------------------------------------------------------------------------------------
    def _ask(self, qid, envs, catch_late):
        """Ask each slot in parallel; {slot: text} for those that answered within the deadline."""
        futures = {self.pool.submit(_collect, self.askers[s], json.dumps(env, ensure_ascii=False),
                                    self.systems.get(s, "")): s for s, env in envs.items()}
        done, not_done = wait(futures, timeout=self.deadline)
        got = {}
        for f in done:
            slot = futures[f]
            try:
                got[slot] = f.result()
            except Exception as e:  # one AI failing must not stop the others
                self.note(f"[{slot}] 응답 없음 {qid}: {type(e).__name__}")
                self._issue(qid, "missing", slot)
        for f in not_done:
            slot = futures[f]
            self.note(f"[{slot}] 응답 없음 {qid}: {self.deadline:g}초 마감")
            self._issue(qid, "missing", slot)
            if catch_late:
                f.add_done_callback(lambda f, slot=slot: self._late(qid, slot, f))
        return got

    def _round(self, qid, question, slots, data, staff, now):
        """Ask the slots; send back once whatever breaks the format or lacks a source. Returns the
        usable [(slot, parsed)], real answers before "모름", in the order of `slots`."""
        envs = {s: envelope(qid, question, [s], data, now) for s in slots}
        got = self._ask(qid, envs, catch_late=True)
        usable, retry = [], {}
        for s in slots:
            if s in got:
                parsed = parse_answer(got[s])
                why = problem(parsed, staff)
                if why:
                    retry[s] = why
                else:
                    usable.append((s, parsed))
        if retry:
            again = {s: {**envs[s], "상태": "반려",
                         "질문": f"{question}\n(반려: {why}. 3줄 형식과 근거의 (출처 시각)을 지켜 다시)"}
                     for s, why in retry.items()}
            got = self._ask(qid, again, catch_late=False)
            for s in retry:
                parsed = parse_answer(got[s]) if s in got else None
                why = problem(parsed, staff) if s in got else "다시 요청에 응답 없음"
                if why:
                    self.note(f"[{s}] 반려 {qid}: {why}")
                    self._issue(qid, "rejected", s)
                else:
                    usable.append((s, parsed))
        usable.sort(key=lambda sp: (sp[1]["결론"].startswith("모름"), slots.index(sp[0])))
        return usable

    def _verify(self, qid, question, checker, lead, data, now):
        """GPT checks Claude's work (code, automation, documents). Returns a 확인 필요 note or None."""
        env = envelope(qid, question, [checker], data, now, status="검증중", review=format_answer(lead[1]))
        got = self._ask(qid, {checker: env}, catch_late=False)
        if checker not in got:
            return f"{checker} 검증 못 함"
        verdict = parse_answer(got[checker])
        if verdict is None:
            return f"{checker} 검증 형식 오류"
        return None if verdict["결론"].startswith("일치") else f"{checker} 검증: {verdict['결론']}"

    def _late(self, qid, slot, future):
        """A late answer goes to the board; Pickle's answer is redone only if it disagrees."""
        try:
            parsed = parse_answer(future.result())
        except Exception:
            return
        if problem(parsed, self.names()[1]):
            return
        self.note(f"[{slot}] 늦은 답 {qid}: {parsed['결론']}")
        with self._lock:
            entry = self.delivered.get(qid)
            if entry is None:
                self.late.setdefault(qid, []).append((slot, parsed))
                return
        items, staff = self.names()
        before = compose(entry["answers"], items | staff, entry["notes"])
        after = compose(entry["answers"] + [(slot, parsed)], items | staff, entry["notes"])
        if after != before:
            entry["answers"].append((slot, parsed))
            entry["reply"](after)
            self._remember(qid, entry["key"], entry["data"], after, self.clock())
            self.status(qid, "완료", f"[완료] {qid} 늦은 답 반영\n{after}", answer=after, late=[slot],
                        key=entry["key"], data=entry["data"], date=self.clock().date().isoformat())

    # -- entry points --------------------------------------------------------------------------------
    def run(self, question, reply, requester="피클"):
        """Answer one free question: reply(text) gets the finished 3 lines. 레미's questions are
        answered later (accept_remy). Returns a record of what happened."""
        start, now = time.perf_counter(), self.clock()
        kind, important = classify(question)
        q = IMPORTANT_RE.sub("", question).strip()
        answerers, checker = plan(kind, important)
        qid, key = self.next_id(now), cache_key(question)
        items, staff = self.names()
        data = gather(q, self.cache_dir, now)
        record = {"id": qid, "question": q, "kind": kind, "important": important, "targets": answerers,
                  "requester": requester, "data": data, "answer": None, "status": "대기"}
        done = dict(key=key, data=data, date=now.date().isoformat(), kind=kind)

        hit = None if important else self.cache.get(key)
        if hit and hit["date"] == now.date().isoformat() and hit["data"] == data:
            reply(hit["answer"])
            self.status(qid, "완료", f"## [완료] {qid} {now:%H:%M} {q} → 캐시 ({hit['id']} 답 재사용)",
                        요청=question, 질문=q, 대상=[], 요청자=requester, answer=hit["answer"], seconds=0.0,
                        cached=True, **done)
            return {**record, "answer": hit["answer"], "status": "완료", "cached": True}

        notes = []
        if self.blocked("GPT") and ("GPT" in answerers or checker == "GPT"):
            answerers = list(dict.fromkeys("Claude" if a == "GPT" else a for a in answerers))
            if checker == "GPT":
                checker = None
                notes.append("GPT 오늘 한도 도달, 검증 못 함")
            record["targets"] = answerers
            self.note(f"[GPT] 오늘 한도 도달 {qid}: Claude로")

        self.status(qid, "대기", f"## [대기] {qid} {now:%H:%M} {q} → {', '.join(answerers)}",
                    요청=question, 질문=q, 대상=answerers, 요청자=requester, important=important, **done)
        if answerers == ["레미"]:
            with self._lock:
                self.pending[qid] = {"request": question, "reply": reply, "key": key, "data": data}
            return record
        slots = [s for s in answerers if s in self.askers]
        if not slots:
            reply(NO_AI)
            self.status(qid, "완료", f"[완료] {qid} {NO_AI}", answer=NO_AI, seconds=0.0, **done)
            return {**record, "answer": NO_AI, "status": "완료"}
        self.status(qid, "처리중")
        answers = self._round(qid, q, slots, data, staff, now)
        if checker and answers:
            if checker in self.askers:
                self.status(qid, "검증중")
                notes.append(self._verify(qid, q, checker, answers[0], data, now))
            else:
                notes.append(f"{checker} 검증 못 함")
        with self._lock:
            answers += self.late.pop(qid, [])
            text = compose(answers, items | staff, notes)
            self.delivered[qid] = {"answers": answers, "notes": notes, "reply": reply, "key": key, "data": data}
        reply(text)
        self._remember(qid, key, data, text, now)
        seconds = round(time.perf_counter() - start, 2)
        code = next((a["code"] for _, a in answers if a["code"]), "")
        issues = self.issues.pop(qid, {"missing": [], "rejected": []})
        self.status(qid, "완료", f"[완료] {qid} {seconds:.1f}초\n{text}" + (f"\n{code}" if code else ""),
                    answer=text, seconds=seconds, answered=[s for s, _ in answers], **issues, **done)
        return {**record, "answer": text, "status": "완료", "seconds": seconds}

    def accept_remy(self, qid, text):
        """레미's one-line answer for a waiting question. Returns a short status for the board."""
        with self._lock:
            entry = self.pending.get(qid)
        if not entry:
            return f"{qid} 대기 질문 없음"
        parsed = parse_answer(REMY_SPLIT_RE.sub("\n", text))
        items, staff = self.names()
        why = problem(parsed, staff)
        if why:
            self.note(f"[레미] 반려 {qid}: {why}")
            return f"{qid} 반려: {why}"
        answer, now = compose([("레미", parsed)], items | staff), self.clock()
        entry["reply"](answer)
        with self._lock:
            self.pending.pop(qid, None)
        self._remember(qid, entry.get("key"), entry.get("data", []), answer, now)
        self.status(qid, "완료", f"[완료] {qid}\n{answer}", answer=answer, answered=["레미"], key=entry.get("key"),
                    data=entry.get("data", []), date=now.date().isoformat(), kind="browser")
        return f"{qid} 완료"
