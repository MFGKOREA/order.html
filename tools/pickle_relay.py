#!/usr/bin/env python3
"""Format and lint messages relayed to Pickle, per CLONE.md. Stdlib only."""
import argparse
import json
import re
import sys
import time
from datetime import datetime
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
}

# Words that must never reach Pickle.
BANNED = ["관제", "결론", "근거", "확인필요", "확인 필요", "전산기준", "전산 기준",
          "안녕하세요", "감사합니다", "수고", "좋은 하루", "참고로", "요약"]

INVENTORY_RE = re.compile(r"^[^:\n]+: 예상 \d+\.\d개$")
SALES_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2} 매장 당일 그로스 세일즈: \d{1,3}(,\d{3})*원 "
    r"\(목표 포캐스트 [\d,]+만 원 대비 \d+\.\d% 달성\)$")
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
    pattern = {"inventory": INVENTORY_RE, "sales": SALES_RE, "boh": BOH_RE, "question": QUESTION_RE}[kind]
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


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dir", default="downloads", help="cache directory (default: downloads)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="check the five cache files exist and parse")
    inv = sub.add_parser("inventory", help="answer for one item")
    inv.add_argument("item")
    sub.add_parser("sales")
    sub.add_parser("boh")
    q = sub.add_parser("question", help="build a board question post")
    q.add_argument("text")
    args = p.parse_args(argv)

    start = time.perf_counter()
    now = datetime.now()
    if args.cmd == "check":
        return 0 if check_cache(args.dir) else 1
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
