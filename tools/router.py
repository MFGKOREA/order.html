#!/usr/bin/env python3
"""Store command router: one plain-language request in, the finished answer out. No AI call.

- Data questions (재고, 매출/그로스, 입고, BOH/근무) are answered from the cache.
- Listed actions (발주, HR 스케줄 확정) go to the action queue that 레미 works through.
  Anything else that sounds like a command is refused, never executed.
- "#3 완료" / "#3 실패 사유" update the queue; "작업 확인" lists it.
- Everything else is a question for the AIs (kind "ask").

Usage: python3 tools/router.py "매장에 감자튀김 재고 몇개야"
"""
import argparse
import difflib
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pickle_relay as pr  # noqa: E402

# Other names people use for an item -> its name in the cache. Extend freely.
ALIASES = {"브로컬리": "브로콜리", "브로꼴리": "브로콜리", "감튀": "감자튀김", "프렌치프라이": "감자튀김"}
UNITS = {"개": "개", "ea": "개", "박스": "박스", "box": "박스", "팩": "팩", "봉지": "봉", "봉": "봉",
         "kg": "kg", "키로": "kg", "병": "병", "캔": "캔", "통": "통"}
KOREAN_NUMBERS = {"한": 1, "하나": 1, "두": 2, "둘": 2, "세": 3, "셋": 3, "네": 4, "넷": 4, "다섯": 5,
                  "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}
DAY_WORDS = [("내일모레", 2), ("모레", 2), ("오늘", 0), ("금일", 0), ("내일", 1), ("명일", 1)]
TOPIC_WORDS = {"inventory": ("재고",), "inbound": ("입고",), "sales": ("그로스", "매출", "세일즈"),
               "boh": ("boh", "근태", "출근", "퇴근", "근무")}
TOPIC_NAMES = {"inventory": "재고", "inbound": "입고", "sales": "매출", "boh": "BOH"}
DEDUPE_SECONDS = 60  # the same pending action again within this window is not queued twice


def _alt(words):
    return "|".join(sorted(map(re.escape, words), key=len, reverse=True))


# "피클에게 ...", "피클아, ...", "루이, ..." are addressing; a bare "피클 재고" is the item (pickles).
ADDRESS_RE = re.compile(r"^\s*(?:피클|루이)\s*(?:(?:에게|한테|아|야)\s*,?|,)\s*")
QTY_RE = re.compile(rf"(\d+(?:\.\d+)?)\s*({_alt(UNITS)})", re.I)
KOREAN_QTY_RE = re.compile(rf"({_alt(KOREAN_NUMBERS)})\s*({_alt(UNITS)})", re.I)
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
MONTH_DAY_RE = re.compile(r"(\d{1,2})\s*(?:/|월)\s*(\d{1,2})")
STATUS_RE = re.compile(r"^#?(\d+)\s*번?\s*(완료|실패)\s*(.*)$")
ASKING_RE = re.compile(r"(몇|얼마|언제|됐어|됐나|했어|했나|했니|인가|일까|어때)")
# Verbs that change something somewhere. Only these make an unlisted request a refused command;
# "확인해줘" or "알려줘" are questions and go on to the AIs.
COMMAND_RE = re.compile(r"(눌러|넣어|보내|올려|등록|취소|바꿔|변경|삭제|결제|승인|진행해|재부팅|재시작|꺼줘|켜줘)")
ORDER_STATUS_RE = re.compile(r"(했어|됐어|됐나|했나|했니|들어갔|넣었|현황|내역|상태)")
SCHEDULE_RE = re.compile(r"(hr|스케[쥴줄]|schedule|근무표)", re.I)
CONFIRM_RE = re.compile(r"(확정|컨펌|confirm)", re.I)
TASKS_RE = re.compile(r"(작업|발주)(확인|현황|상태|내역|목록)")
JOSA_RE = re.compile(r"(이랑|하고|에서|으로|은|는|이|가|을|를|도|만|의|랑|에|로)$")
DATA_ERRORS = (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError)


@dataclass
class Reply:
    kind: str  # inventory, inbound, sales, boh, multi, order, hr_confirm, status, tasks, held, not_allowed, ask
    text: str  # finished line(s) for Pickle; empty when kind is "ask"
    actions: tuple = ()  # actions this request queued


class ActionQueue:
    """Append-only action log (JSON lines) that 레미 works through. Re-reads when another process writes."""

    def __init__(self, path):
        self.path = Path(path)
        self.items, self._stamp = {}, None
        self.version = 0  # goes up on every change, so a view is rebuilt only when needed
        self.refresh()

    def refresh(self):
        try:
            st = self.path.stat()
        except FileNotFoundError:
            return
        if (st.st_mtime_ns, st.st_size) == self._stamp:
            return
        items = {}
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                items.setdefault(rec["id"], {}).update(rec)
        self.items, self._stamp = items, (st.st_mtime_ns, st.st_size)
        self.version += 1

    def _append(self, rec):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.items.setdefault(rec["id"], {}).update(rec)
        st = self.path.stat()
        self._stamp = (st.st_mtime_ns, st.st_size)
        self.version += 1

    def add(self, action, now):
        """Queue an action; returns (id, duplicate). A pending twin within DEDUPE_SECONDS is reused."""
        self.refresh()
        for a in self.items.values():
            age = (now - datetime.fromisoformat(a["at"])).total_seconds()
            if a["status"] == "접수" and a["text"] == action["text"] and 0 <= age <= DEDUPE_SECONDS:
                return a["id"], True
        new_id = max(self.items, default=0) + 1
        self._append({"id": new_id, "at": now.isoformat(timespec="seconds"), "status": "접수", "note": "",
                      **action})
        return new_id, False

    def set_status(self, task_id, status, note, now):
        self.refresh()
        if task_id not in self.items:
            return False
        self._append({"id": task_id, "status": status, "note": note,
                      "updated_at": now.isoformat(timespec="seconds")})
        return True

    def view(self, finished=3):
        """Every pending (접수) action plus the latest `finished` done or failed ones, oldest first,
        e.g. '#3 접수 14:05 발주 브로콜리 2개'. Short, so Pickle and 레미 read few tokens."""
        self.refresh()
        ordered = sorted(self.items.values(), key=lambda a: a["id"])
        done_ids = {a["id"] for a in ordered if a["status"] != "접수"}
        keep = {a["id"] for a in ordered if a["status"] == "접수"} | set(sorted(done_ids)[-finished:] if finished else ())
        lines = []
        for a in ordered:
            if a["id"] in keep:
                note = f" ({a['note']})" if a.get("note") else ""
                lines.append(f"#{a['id']} {a['status']} {datetime.fromisoformat(a['at']):%H:%M} {a['text']}{note}")
        return lines


def known_items(cache_dir):
    """Item names the cache knows (inventory and deliveries)."""
    names = set()
    for key, field in (("inventory", "items"), ("inbound", "deliveries")):
        try:
            names.update(i["name"] for i in pr.load(cache_dir, key)[field])
        except DATA_ERRORS:
            pass
    return names


def find_items(text, names):
    """Items named in text, in order: exact names with spaces ignored (longest first, so 피자치즈
    is not read as 치즈), then aliases, then close misspellings."""
    compact = re.sub(r"\s+", "", text)
    found, taken = [], []
    for word, name in sorted([(n, n) for n in names] + list(ALIASES.items()), key=lambda c: -len(c[0])):
        for m in re.finditer(re.escape(re.sub(r"\s+", "", word)), compact):
            if not any(s < m.end() and m.start() < e for s, e in taken):
                taken.append((m.start(), m.end()))
                found.append((m.start(), name))
    if not found and names:
        for m in re.finditer(r"[가-힣A-Za-z]+", text):
            close = difflib.get_close_matches(JOSA_RE.sub("", m.group()), sorted(names), n=1, cutoff=0.75)
            if close:
                found.append((m.start(), close[0]))
    return list(dict.fromkeys(name for _, name in sorted(found)))


def find_date(text, today):
    for word, offset in DAY_WORDS:
        if word in text:
            return today + timedelta(days=offset)
    m = MONTH_DAY_RE.search(text)
    if m:
        try:
            d = date(today.year, int(m[1]), int(m[2]))
        except ValueError:
            return None
        return d.replace(year=d.year + 1) if (today - d).days > 180 else d  # "1/3" asked in December
    return None


def parse_quantities(text):
    """[(qty, unit)] in order of appearance: "2개", "3박스", "두 박스", or one bare number."""
    found = [(m.start(), float(m[1]), UNITS[m[2].lower()]) for m in QTY_RE.finditer(text)]
    if not found:
        found = [(m.start(), KOREAN_NUMBERS[m[1]], UNITS[m[2].lower()]) for m in KOREAN_QTY_RE.finditer(text)]
    if not found:
        bare = NUMBER_RE.findall(text)
        if len(bare) == 1:
            found = [(0, float(bare[0]), "개")]
    return [(q, u) for _, q, u in sorted(found)]


def _queued(queue, action, now, label):
    task_id, duplicate = queue.add(action, now)
    return f"{label} #{task_id}" if not duplicate else f"{label} #{task_id} (이미 접수됨)"


def _order(t, cache_dir, now, queue):
    items, qtys = find_items(t, known_items(cache_dir)), parse_quantities(t)
    if not items:
        return Reply("held", "발주 보류: 품목을 못 찾음")
    if not qtys:
        return Reply("held", f"발주 보류: {items[0]} 수량을 못 찾음")
    if len(items) == len(qtys):
        pairs = list(zip(items, qtys))
    elif len(items) == 1:
        pairs = [(items[0], qtys[0])]
    else:
        return Reply("held", f"발주 보류: 품목 {len(items)}개와 수량 {len(qtys)}개가 짝이 안 맞음")
    lines, actions = [], []
    for item, (qty, unit) in pairs:
        if qty <= 0:
            lines.append(f"발주 보류: {item} 수량 0")
            continue
        amount = f"{pr.fmt_qty(qty)}{unit}"
        action = {"type": "order", "item": item, "qty": qty, "unit": unit, "text": f"발주 {item} {amount}"}
        task_id, duplicate = queue.add(action, now)
        lines.append(f"발주 접수 #{task_id}: {item} {amount}" + (" (이미 접수됨)" if duplicate else ""))
        actions.append(action)
    return Reply("order" if actions else "held", "\n".join(lines), tuple(actions))


def _inventory(items, t, cache_dir, now):
    data = {i["name"]: i for i in pr.load(cache_dir, "inventory")["items"]}
    if not items:
        return [pr.fmt_inventory(i, now) for i in data.values()]
    return [pr.fmt_inventory(data[n], now) if n in data else f"{n}: 재고 데이터 없음" for n in items]


def _inbound(items, t, cache_dir, now):
    today, totals = now.date(), pr.inbound_totals(pr.load(cache_dir, "inbound"))
    day = find_date(t, today)
    if not items:
        lines = [pr.fmt_inbound(name, d, q, u, today) for (d, name), (q, u) in sorted(totals.items())
                 if (d == day if day else 0 <= (d - today).days < 7)]
        return lines or [f"{pr.day_label(day, today) if day else '7일 내'} 입고 없음"]
    lines = []
    for n in items:
        if day:
            qty, unit = totals.get((day, n), (None, "개"))
            lines.append(pr.fmt_inbound(n, day, qty, unit, today))
            continue
        upcoming = sorted((d, q, u) for (d, name), (q, u) in totals.items() if name == n and d >= today)
        lines.append(pr.fmt_inbound(n, *upcoming[0], today) if upcoming else f"{n}: 입고 예정 없음")
    return lines


def _sales(items, t, cache_dir, now):
    return [pr.fmt_sales(pr.load(cache_dir, "sales"))]


def _boh(items, t, cache_dir, now):
    return [pr.fmt_boh(pr.load(cache_dir, "boh"))]


ANSWERS = {"inventory": _inventory, "inbound": _inbound, "sales": _sales, "boh": _boh}


def route(text, cache_dir, queue, now=None):
    now = now or datetime.now()
    t = ADDRESS_RE.sub("", text.strip(), count=1)
    compact = re.sub(r"\s+", "", t).lower()
    asking = bool(ASKING_RE.search(compact))

    m = STATUS_RE.match(t)
    if m:
        done = queue.set_status(int(m[1]), m[2], m[3].strip(), now)
        return Reply("status", f"#{m[1]} {m[2]} 처리" if done else f"#{m[1]} 작업 없음")
    if TASKS_RE.search(compact) or ("발주" in compact and ORDER_STATUS_RE.search(compact)):
        return Reply("tasks", "\n".join(queue.view()) or "작업 없음")
    if "발주" in compact:
        # "발주량?", "몇 개 발주해야 해?" ask for advice; an order names a quantity or is a plain command.
        if asking or "발주량" in compact or "얼마나" in compact or (compact.endswith("?") and not parse_quantities(t)):
            return Reply("ask", "")
        return _order(t, cache_dir, now, queue)
    if SCHEDULE_RE.search(compact) and CONFIRM_RE.search(compact) and not asking:
        action = {"type": "hr_confirm", "text": "HR 스케줄 확정"}
        return Reply("hr_confirm", _queued(queue, action, now, "HR 스케줄 확정 접수"), (action,))

    topics = [k for k, words in TOPIC_WORDS.items() if any(w in compact for w in words)]
    if topics:
        items, lines = find_items(t, known_items(cache_dir)), []
        for k in topics:
            try:
                lines += ANSWERS[k](items, t, cache_dir, now)
            except DATA_ERRORS:
                lines.append(f"{TOPIC_NAMES[k]} 데이터 없음")
        return Reply(topics[0] if len(topics) == 1 else "multi", "\n".join(lines))
    if COMMAND_RE.search(compact) and not asking:
        return Reply("not_allowed", f"등록 안 된 작업: {t}")
    return Reply("ask", "")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dir", default="downloads", help="cache directory (default: downloads)")
    p.add_argument("--queue", help="action log (default: <dir>/.hub/actions.jsonl)")
    p.add_argument("text", nargs="+", help="the request, as Pickle would pass it on")
    args = p.parse_args(argv)
    queue = ActionQueue(args.queue or Path(args.dir) / ".hub" / "actions.jsonl")
    start = time.perf_counter()
    reply = route(" ".join(args.text), args.dir, queue)
    ms = (time.perf_counter() - start) * 1000
    if reply.text:
        print(reply.text)
    print(f"({reply.kind}, {ms:.2f} ms)", file=sys.stderr)
    if reply.kind == "ask":
        print("AI question: run it through tools/hub.py --ai or tools/ai_board.py ask", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
