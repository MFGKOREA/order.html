#!/usr/bin/env python3
"""Shared AI board: post a question with answer slots, auto-fill Claude/GPT, relay to Pickle."""
import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pickle_relay as pr  # noqa: E402

SLOTS = ["Claude", "GPT", "레미"]  # 레미 (Grokbot) fills its own slot from the Grok Bot app
AUTO = ["Claude", "GPT"]
SINGLE_LIMIT = 3.0  # seconds per AI answer
TOTAL_LIMIT = 10.0  # seconds from question to relay-ready message

SYSTEM = ("매장 운영 질문에 답한다. 인사·덕담·사족 없이 핵심 데이터만 한두 줄로 쓴다. "
          "'결론', '근거', '확인필요' 같은 라벨이나 머리글은 붙이지 않는다. '관제'라는 단어는 쓰지 않는다.")

HEAD_RE = re.compile(r"^## 질문: \[(?P<at>[^\]]+)\] (?P<q>.*)$")
SLOT_RE = re.compile(r"^\[(?P<name>[^\]]+)\] 답변:[ \t]*(?P<text>.*)$")


def post(question, now):
    return pr.fmt_question(question, now) + "\n" + "\n".join(f"[{s}] 답변:" for s in SLOTS)


def parse(board):
    """Split board text into question blocks, oldest first."""
    blocks, cur, slot = [], None, None
    for line in board.splitlines():
        m = HEAD_RE.match(line)
        if m:
            cur = {"head": [line], "question": m["q"].strip(), "answers": {}}
            blocks.append(cur)
            slot = None
            continue
        if cur is None:
            continue
        m = SLOT_RE.match(line)
        if m:
            slot = m["name"]
            cur["answers"][slot] = m["text"].strip()
        elif slot:
            cur["answers"][slot] = (cur["answers"][slot] + "\n" + line).strip()
        elif line.startswith("- "):
            cur["head"].append(line)
    return blocks


def render(block):
    lines = list(block["head"])
    for name, text in block["answers"].items():
        first, *rest = (text or "").split("\n")
        lines.append(f"[{name}] 답변: {first}".rstrip())
        lines.extend(rest)
    return "\n".join(lines)


def fill(block, askers):
    """Ask every empty AUTO slot in parallel. Returns {slot: (seconds, error or None)}."""
    todo = [s for s in AUTO if s in askers and not block["answers"].get(s)]

    def run(slot):
        start = time.perf_counter()
        try:
            answer, err = askers[slot](block["question"], SYSTEM), None
        except Exception as e:  # report per slot; one AI failing must not block the others
            answer, err = "", f"{type(e).__name__}: {e}"
        return slot, answer, time.perf_counter() - start, err

    timings = {}
    with ThreadPoolExecutor(max_workers=len(todo) or 1) as pool:
        for slot, answer, secs, err in pool.map(run, todo):
            block["answers"][slot] = answer
            timings[slot] = (secs, err)
    return timings


def relay(block):
    """Core data lines for Pickle: filler and labels stripped, duplicates dropped, empty slots skipped."""
    lines = []
    for text in block["answers"].values():
        for line in pr.strip_filler(text or "").splitlines():
            if line not in lines:
                lines.append(line)
    msg = "\n".join(lines)
    errors = [f"banned word: {w}" for w in pr.BANNED if w in msg]
    return msg, errors


def speed_report(timings, total):
    out = []
    for slot, (secs, err) in timings.items():
        status = f"FAIL {err}" if err else ("OK" if secs <= SINGLE_LIMIT else f"OVER {SINGLE_LIMIT:.0f}s")
        out.append(f"{slot}: {secs:.2f}s {status}")
    out.append(f"total: {total:.2f}s {'OK' if total <= TOTAL_LIMIT else f'OVER {TOTAL_LIMIT:.0f}s'}")
    return out


def default_askers():
    from ask_claude import ask as claude
    from ask_gpt import ask as gpt
    return {"Claude": claude, "GPT": gpt}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("post", help="print a question post with answer slots").add_argument("text")
    sub.add_parser("answer", help="fill empty Claude/GPT slots of the latest question").add_argument("board")
    sub.add_parser("relay", help="print the Pickle message for the latest question").add_argument("board")
    sub.add_parser("ask", help="post + answer + relay in one go, with timings").add_argument("text")
    args = p.parse_args(argv)

    if args.cmd == "post":
        print(post(args.text, datetime.now()))
        return 0

    start = time.perf_counter()
    if args.cmd == "ask":
        block = parse(post(args.text, datetime.now()))[-1]
    else:
        blocks = parse(Path(args.board).read_text(encoding="utf-8"))
        if not blocks:
            print("no '## 질문:' block found", file=sys.stderr)
            return 1
        block = blocks[-1]

    if args.cmd in ("answer", "ask"):
        timings = fill(block, default_askers())
        print(render(block))
        for line in speed_report(timings, time.perf_counter() - start):
            print(line, file=sys.stderr)
        if args.cmd == "answer":
            return 1 if any(err for _, err in timings.values()) else 0
        print("---")

    msg, errors = relay(block)
    print(msg)
    for e in errors:
        print(f"LINT: {e}", file=sys.stderr)
    return 1 if errors or not msg else 0


if __name__ == "__main__":
    sys.exit(main())
