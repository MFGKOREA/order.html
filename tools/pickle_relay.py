#!/usr/bin/env python3
"""Format and lint messages relayed to Pickle, per CLONE.md. Stdlib only."""
import argparse
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

BOARD_DOC_ID = "123Xl37_ffN18WCPpWas_cn94G4ibAtfeHtWn8IgkiQo"
BOARD_TARGETS = "Claude, 그록봇, GPT, 피클(루이)"
BOARD_SPEED = "단일 3초 내, 2중 전달 10초 안쪽 완료"

CACHE_FILES = {
    "recipes": "line_recipes.json",
    "promotions": "store_promotions.json",
    "inventory": "live_inventory_cache.json",
    "boh": "live_boh_status.json",
    "sales": "live_sales.json",
    "inbound": "live_inbound.json",
}

# Words that must never reach Pickle.
BANNED = ["관제", "결론", "근거", "확인필요", "확인 필요", "전산기준", "전산 기준",
          "안녕하세요", "감사합니다", "수고", "좋은 하루", "참고로", "요약"]

INVENTORY_RE = re.compile(r"^[^:\n]+: 예상 \d+\.\d개$")
SALES_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2} 매장 당일 그로스 세일즈: \d{1,3}(,\d{3})*원 "
    r"\(목표 포캐스트 [\d,]+만 원 대비 \d+\.\d% 달성\)$")
INBOUND_RE = re.compile(
    r"^[^:\n]+: (?:(?:오늘|내일|모레)\(\d{1,2}/\d{1,2}\)|\d{1,2}/\d{1,2}) 입고 (?:\d+(?:\.\d)?\D+|없음)$")
BOH_RE = re.compile(
    r"^\[BOH 리포트 \(\d{2}:\d{2}\)\]\n"
    r"- 신규 출근/퇴근: .+\n"
    r"- 근무 중: \d+명\n"
    r"- 퇴근 완료: \d+명\n"
    r"- 특이사항: .+$")
QUESTION_RE = re.compile(
    r"^## 질문: \[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] .+\n"
    rf"- 대상: {re.escape(BOARD_TARGETS)}\n"
    rf"- 속도 기준: {re.escape(BOARD_SPEED)}$")


def r1(x):
    """Round half up to one decimal (81.25 -> 81.3), unlike Python's banker's rounding."""
    return Decimal(str(x)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def estimate_stock(item, now):
    hours = (now - datetime.fromisoformat(item["snapshot_at"])).total_seconds() / 3600
    left = item["on_hand"] - item.get("reserved", 0) - item.get("burn_per_hour", 0) * max(hours, 0)
    return max(left, 0.0)


def fmt_inventory(item, now):
    return f"{item['name']}: 예상 {r1(estimate_stock(item, now))}개"


def fmt_sales(s):
    gross = int(s["gross_sales"])
    forecast = s["forecast_manwon"]
    pct = gross / (forecast * 10_000) * 100
    return (f"{s['date']} 매장 당일 그로스 세일즈: {gross:,}원 "
            f"(목표 포캐스트 {forecast:,}만 원 대비 {r1(pct)}% 달성)")


def fmt_qty(q):
    return str(int(q)) if float(q).is_integer() else str(r1(q))


def day_label(d, today):
    md = f"{d.month}/{d.day}"
    word = {0: "오늘", 1: "내일", 2: "모레"}.get((d - today).days)
    return f"{word}({md})" if word else md


def fmt_inbound(name, d, qty, unit, today):
    """피자치즈: 내일(11/14) 입고 6개  /  피자치즈: 내일(11/14) 입고 없음 (qty None)"""
    amount = "없음" if qty is None else f"{fmt_qty(qty)}{unit}"
    return f"{name}: {day_label(d, today)} 입고 {amount}"


def inbound_totals(data):
    """{(date, name): (qty, unit)}, with same-day deliveries of one item added up."""
    totals = {}
    for d in data["deliveries"]:
        key = (date.fromisoformat(d["date"]), d["name"])
        qty, unit = totals.get(key, (0, d.get("unit", "개")))
        totals[key] = (qty + d["qty"], unit)
    return totals


def inbound_lines(data, today, days=7):
    """Deliveries from today through the next `days - 1` days, by date then item."""
    return [fmt_inbound(name, d, qty, unit, today)
            for (d, name), (qty, unit) in sorted(inbound_totals(data).items())
            if 0 <= (d - today).days < days]


def fmt_boh(b):
    events = ", ".join(f"{e['shift']} {e['name']} ({e['type']} {e['time']})" for e in b.get("events", []))
    notes = b.get("notes") or "없음"
    return "\n".join([
        f"[BOH 리포트 ({b['as_of']})]",
        f"- 신규 출근/퇴근: {events or '없음'}",
        f"- 근무 중: {b['on_duty']}명",
        f"- 퇴근 완료: {b['off_duty']}명",
        f"- 특이사항: {notes}",
    ])


def fmt_question(text, now):
    return "\n".join([
        f"## 질문: [{now:%Y-%m-%d %H:%M}] {text.strip()}",
        f"- 대상: {BOARD_TARGETS}",
        f"- 속도 기준: {BOARD_SPEED}",
    ])


def strip_filler(answer):
    """Reduce a collected AI answer to its data lines before relaying."""
    keep = []
    for line in answer.splitlines():
        line = re.sub(r"^\s*(#+\s*)?(결론|근거|확인\s?필요|요약|참고)\s*[:：]\s*", "", line).strip()
        if not line or any(w in line for w in ("안녕하세요", "감사합니다", "수고", "좋은 하루")):
            continue
        keep.append(line)
    return "\n".join(keep)


def lint(msg, kind):
    """Return a list of rule violations (empty list = pass)."""
    errors = [f"banned word: {w}" for w in BANNED if w in msg]
    pattern = {"inventory": INVENTORY_RE, "sales": SALES_RE, "inbound": INBOUND_RE, "boh": BOH_RE,
               "question": QUESTION_RE}[kind]
    if not pattern.match(msg):
        errors.append(f"does not match {kind} format")
    if kind == "inventory" and re.search(r"\d{1,2}:\d{2}", msg):
        errors.append("inventory answer contains a timestamp")
    return errors


def load(cache_dir, key):
    return json.loads((Path(cache_dir) / CACHE_FILES[key]).read_text(encoding="utf-8"))


def check_cache(cache_dir):
    ok = True
    for key, name in CACHE_FILES.items():
        path = Path(cache_dir) / name
        try:
            json.loads(path.read_text(encoding="utf-8"))
            print(f"OK       {path}")
        except FileNotFoundError:
            print(f"MISSING  {path}")
            ok = False
        except json.JSONDecodeError as e:
            print(f"BAD JSON {path}: {e}")
            ok = False
    return ok


FEED_KEYS = ("inventory", "sales", "inbound", "boh")
# Small files, so Pickle reads only the one it needs: one per topic, plus inventory split by the
# item's first consonant (감자튀김 -> 재고_ㄱ.txt) and deliveries split by day (입고_내일.txt).
BASE_FILES = {"inventory": "재고.txt", "sales": "매출.txt", "inbound": "입고.txt", "boh": "BOH.txt"}
DAY_FILES = {0: "입고_오늘.txt", 1: "입고_내일.txt", 2: "입고_모레.txt"}
CHOSEONG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"


def initial(name):
    """First consonant of an item name (감자튀김 -> ㄱ); a Latin letter upper-cased; else 기타."""
    ch = name.strip()[:1]
    if "가" <= ch <= "힣":
        return CHOSEONG[(ord(ch) - ord("가")) // 588]
    if ch.isascii() and ch.isalpha():
        return ch.upper()
    return "기타"


def _topic_files(key, cache_dir, now):
    """{file name: [(message, kind)]} for one topic; the first file holds every message."""
    if key == "inventory":
        files = {BASE_FILES[key]: []}
        for item in load(cache_dir, key)["items"]:
            msg = (fmt_inventory(item, now), "inventory")
            files[BASE_FILES[key]].append(msg)
            files.setdefault(f"재고_{initial(item['name'])}.txt", []).append(msg)
        return files
    if key == "sales":
        return {BASE_FILES[key]: [(fmt_sales(load(cache_dir, key)), "sales")]}
    if key == "inbound":
        data, today = load(cache_dir, key), now.date()
        files = {BASE_FILES[key]: [(line, "inbound") for line in inbound_lines(data, today)]}
        totals = inbound_totals(data)
        for offset, name in DAY_FILES.items():
            day = today + timedelta(days=offset)
            files[name] = [(fmt_inbound(item, d, q, u, today), "inbound")
                           for (d, item), (q, u) in sorted(totals.items()) if d == day]
        return files
    return {BASE_FILES[key]: [(fmt_boh(load(cache_dir, key)), "boh")]}


def feed_sections(cache_dir, now):
    """Every ready-made answer: {topic: {file name: text}}, so Pickle reads instead of asking.

    Returns (sections, broken, problems): a missing cache file has no section; a file that does
    not parse (e.g. caught mid-write) is listed in `broken`.
    """
    sections, broken, problems = {}, set(), []
    for key in FEED_KEYS:
        try:
            files = _topic_files(key, cache_dir, now)
        except FileNotFoundError:
            problems.append(f"missing {CACHE_FILES[key]}")
            continue
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            broken.add(key)
            problems.append(f"unreadable {CACHE_FILES[key]}: {type(e).__name__}: {e}")
            continue
        for msg, kind in files[BASE_FILES[key]]:  # the other files only repeat these
            problems.extend(f"{CACHE_FILES[key]}: {e}" for e in lint(msg, kind))
        sections[key] = {name: "\n".join(m for m, _ in msgs) for name, msgs in files.items()}
    return sections, broken, problems


def topic_texts(sections, known=()):
    """{file name: text} to write. A file without data reads "없음", so none goes stale; `known`
    names files written before (e.g. 재고_ㅎ.txt after its last item is gone)."""
    texts = {name: "없음\n" for name in known}
    for key in FEED_KEYS:
        files = sections.get(key) or {BASE_FILES[key]: ""}
        texts.update({name: (text or "없음") + "\n" for name, text in files.items()})
    return texts


def write_topics(out_dir, sections, last=None):
    """Write each answer file whose text changed; returns the names written.

    `last` (a dict kept by the caller) remembers what was written, so unchanged files are not
    even read back from the Drive folder.
    """
    written = []
    for name, text in topic_texts(sections, last or ()).items():
        if last is not None and last.get(name) == text:
            continue
        if write_if_changed(Path(out_dir) / name, text):
            written.append(name)
        if last is not None:
            last[name] = text
    return written


def write_if_changed(path, text):
    """Atomically replace `path` with `text`, only when it differs (no needless Drive re-syncs)."""
    path = Path(path)
    try:
        if path.read_text(encoding="utf-8") == text:
            return False
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    for attempt in range(20):
        try:
            os.replace(tmp, path)  # readers see the old file or the new one, never half of it
            return True
        except PermissionError:  # Windows: a sync client can hold the file for a moment
            if attempt == 19:
                raise
            time.sleep(0.05)


class Feed:
    """Keeps the topic files in step with the cache. One step() costs well under a millisecond."""

    def __init__(self, cache_dir, out_dir):
        self.cache_dir, self.out_dir = cache_dir, out_dir
        self.last_good, self.last_texts = {}, {}

    def step(self, now=None):
        """Rebuild every answer; write the topics that changed. Returns (written, problems)."""
        sections, broken, problems = feed_sections(self.cache_dir, now or datetime.now())
        # A file caught mid-write keeps its last good answers; a deleted file reads "없음".
        self.last_good = {**sections, **{k: self.last_good[k] for k in broken if k in self.last_good}}
        # Nothing readable at all (wrong folder, cache not written yet): leave the files alone.
        written = write_topics(self.out_dir, self.last_good, self.last_texts) if self.last_good else []
        return written, problems


def watch_feed(cache_dir, out_dir, interval=0.1, stop=None, log=None):
    """Rebuild every `interval` seconds and rewrite each topic file whenever its answers change.

    A rebuild costs ~0.06 ms, so a short interval is nearly free, and files in the Drive folder
    are only touched when an answer changes.
    """
    log = log or sys.stderr
    feed, last_problems = Feed(cache_dir, out_dir), None
    while True:
        t0 = time.perf_counter()
        written, problems = feed.step()
        if written:
            ms = (time.perf_counter() - t0) * 1000
            print(f"{datetime.now():%H:%M:%S} updated {', '.join(written)} ({ms:.1f} ms)", file=log, flush=True)
        if problems != last_problems:
            for p in problems:
                print(f"  {p}", file=log, flush=True)
            last_problems = problems
        if stop and stop():
            return
        time.sleep(interval)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", default="downloads", help="cache directory (default: downloads)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="check the cache files exist and parse")
    inv = sub.add_parser("inventory", help="answer for one item")
    inv.add_argument("item")
    sub.add_parser("sales")
    sub.add_parser("boh")
    q = sub.add_parser("question", help="build a board question post")
    q.add_argument("text")
    f = sub.add_parser("feed", help="write every ready-made answer into the topic files Pickle reads")
    f.add_argument("--out-dir", help="folder for the answer files (재고.txt, 재고_ㄱ.txt, 매출.txt, 입고.txt, "
                                     "입고_내일.txt, BOH.txt, ...) (default: <dir>/pickle); "
                                     "use the Drive folder Pickle reads")
    f.add_argument("--watch", action="store_true", help="keep running; rewrite a file whenever its answers change")
    f.add_argument("--interval", type=float, default=0.1, help="seconds between checks with --watch (default 0.1)")
    args = p.parse_args(argv)

    start = time.perf_counter()
    now = datetime.now()
    if args.cmd == "check":
        return 0 if check_cache(args.dir) else 1
    if args.cmd == "feed":
        out_dir = args.out_dir or str(Path(args.dir) / "pickle")
        if args.watch:
            try:
                watch_feed(args.dir, out_dir, args.interval)
            except KeyboardInterrupt:
                return 0
        sections, broken, problems = feed_sections(args.dir, now)
        if sections:
            written = write_topics(out_dir, sections)
            ms = (time.perf_counter() - start) * 1000
            print(f"{'updated ' + ', '.join(written) if written else 'unchanged'} in {out_dir} ({ms:.1f} ms)",
                  file=sys.stderr)
        else:
            print(f"nothing readable in {args.dir}; {out_dir} left as it was", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1 if problems else 0
    if args.cmd == "inventory":
        items = {i["name"]: i for i in load(args.dir, "inventory")["items"]}
        if args.item not in items:
            print(f"unknown item: {args.item}", file=sys.stderr)
            return 1
        msg, kind = fmt_inventory(items[args.item], now), "inventory"
    elif args.cmd == "sales":
        msg, kind = fmt_sales(load(args.dir, "sales")), "sales"
    elif args.cmd == "boh":
        msg, kind = fmt_boh(load(args.dir, "boh")), "boh"
    else:
        msg, kind = fmt_question(args.text, now), "question"

    errors = lint(msg, kind)
    print(msg)
    ms = (time.perf_counter() - start) * 1000
    print(f"({ms:.1f} ms)", file=sys.stderr)
    for e in errors:
        print(f"LINT: {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
