#!/usr/bin/env python3
"""Shared AI board: post a question with answer slots, stream Claude/GPT answers, relay to Pickle."""
import argparse
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pickle_relay as pr  # noqa: E402

SLOTS = ["Claude", "GPT", "레미"]  # 레미 (Grokbot) fills its own slot from the Grok Bot app
AUTO = ["Claude", "GPT"]
SINGLE_LIMIT = 3.0  # seconds until each AI's first useful line
TOTAL_LIMIT = 10.0  # seconds from question until every AI is done

SYSTEM = ("매장 운영 질문에 답한다. 인사·덕담·사족 없이 핵심 데이터만 한 줄로 쓴다. "
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


def banned_in(line):
    return [w for w in pr.BANNED if w in line]


def fill(block, askers, on_line=None):
    """Stream every empty AUTO slot in parallel.

    askers[slot](question, system) yields answer lines as they arrive. on_line(slot, line) fires for
    each useful line the moment it arrives, fastest AI first, from worker threads.
    Returns {slot: {"first": seconds, "done": seconds, "error": str or None}}.
    """
    todo = [s for s in AUTO if s in askers and not block["answers"].get(s)]
    start = time.perf_counter()
    stats = {s: {"first": None, "done": None, "error": None} for s in todo}

    def run(slot):
        parts = []
        try:
            for line in askers[slot](block["question"], SYSTEM):
                parts.append(line)
                useful = pr.strip_filler(line)
                if useful:
                    if stats[slot]["first"] is None:
                        stats[slot]["first"] = time.perf_counter() - start
                    if on_line:
                        on_line(slot, useful)
            answer = "\n".join(parts).strip()
        except Exception as e:  # one AI failing must not block the others; its partial answer is dropped
            stats[slot]["error"] = f"{type(e).__name__}: {e}"
            answer = ""
        stats[slot]["done"] = time.perf_counter() - start
        return slot, answer

    if todo:
        with ThreadPoolExecutor(max_workers=len(todo)) as pool:
            for fut in as_completed([pool.submit(run, s) for s in todo]):
                slot, answer = fut.result()
                block["answers"][slot] = answer
    return stats


def relay(block):
    """Pickle message for a block: filler stripped, duplicates dropped, empty slots skipped.

    Returns (message, withheld) where withheld are lines held back for containing banned words.
    """
    lines, withheld = [], []
    for text in block["answers"].values():
        for line in pr.strip_filler(text or "").splitlines():
            if banned_in(line):
                withheld.append(line)
            elif line not in lines:
                lines.append(line)
    return "\n".join(lines), withheld


def speed_report(stats, total):
    out = []
    for slot, st in stats.items():
        if st["error"]:
            out.append(f"{slot}: FAIL after {st['done']:.2f}s {st['error']}")
        elif st["first"] is None:
            out.append(f"{slot}: no useful line ({st['done']:.2f}s)")
        else:
            ok = "OK" if st["first"] <= SINGLE_LIMIT else f"OVER {SINGLE_LIMIT:.0f}s"
            out.append(f"{slot}: first line {st['first']:.2f}s {ok}, done {st['done']:.2f}s")
    firsts = [st["first"] for st in stats.values() if st["first"] is not None]
    if firsts:
        out.append(f"first to Pickle: {min(firsts):.2f}s")
    out.append(f"total: {total:.2f}s {'OK' if total <= TOTAL_LIMIT else f'OVER {TOTAL_LIMIT:.0f}s'}")
    return out


def run_ask(question, askers, out=None, err=None):
    """Answer one question. Pickle lines go to `out` the moment they arrive; then the filled board block."""
    out, err = out or sys.stdout, err or sys.stderr
    start = time.perf_counter()
    block = parse(post(question, datetime.now()))[-1]
    sent, withheld, lock = [], [], threading.Lock()

    def push(slot, line):
        with lock:
            if banned_in(line):
                withheld.append(line)
            elif line not in sent:
                sent.append(line)
                print(line, file=out, flush=True)

    stats = fill(block, askers, on_line=push)
    total = time.perf_counter() - start
    print("---", file=out)
    print(render(block), file=out, flush=True)
    for line in speed_report(stats, total):
        print(line, file=err)
    for line in withheld:
        print(f"WITHHELD (banned word {', '.join(banned_in(line))}): {line}", file=err)
    failed = any(st["error"] for st in stats.values())
    return 0 if sent and not failed else 1


def _warm(item):
    name, fn = item
    try:
        fn()
        return name, None
    except Exception as e:  # warm-up is best effort; a failure here is an early warning (e.g. missing key)
        return name, f"{type(e).__name__}: {e}"


def serve(askers, warmers, inp=None, out=None, err=None):
    """Stay resident: SDKs load once and connections stay open, so each question skips that setup."""
    inp, err = inp or sys.stdin, err or sys.stderr
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(warmers) or 1) as pool:
        for name, error in pool.map(_warm, warmers.items()):
            print(f"warm {name}: {error or 'OK'}", file=err)
    print(f"ready in {time.perf_counter() - start:.2f}s; one question per line", file=err, flush=True)
    for line in inp:
        if line.strip():
            run_ask(line.strip(), askers, out, err)
    return 0


def load_ais():
    import ask_claude
    import ask_gpt
    return ({"Claude": ask_claude.lines, "GPT": ask_gpt.lines},
            {"Claude": ask_claude.warm, "GPT": ask_gpt.warm})


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("post", help="print a question post with answer slots").add_argument("text")
    sub.add_parser("answer", help="fill empty Claude/GPT slots of the latest question").add_argument("board")
    sub.add_parser("relay", help="print the Pickle message for the latest question").add_argument("board")
    sub.add_parser("ask", help="answer one question now; Pickle lines stream as they arrive").add_argument("text")
    sub.add_parser("serve", help="stay resident and answer one question per stdin line (fastest)")
    args = p.parse_args(argv)

    if args.cmd == "post":
        print(post(args.text, datetime.now()))
        return 0

    if args.cmd in ("answer", "relay"):
        blocks = parse(Path(args.board).read_text(encoding="utf-8"))
        if not blocks:
            print("no '## 질문:' block found", file=sys.stderr)
            return 1
        block = blocks[-1]
        if args.cmd == "relay":
            msg, withheld = relay(block)
            print(msg)
            for line in withheld:
                print(f"WITHHELD (banned word {', '.join(banned_in(line))}): {line}", file=sys.stderr)
            return 0 if msg else 1

    t0 = time.perf_counter()
    askers, warmers = load_ais()
    startup = time.perf_counter() - t0

    if args.cmd == "serve":
        return serve(askers, warmers)
    if args.cmd == "ask":
        print(f"startup: {startup:.2f}s (serve skips this)", file=sys.stderr)
        return run_ask(args.text, askers)

    start = time.perf_counter()  # answer
    stats = fill(block, askers)
    print(render(block))
    for line in speed_report(stats, time.perf_counter() - start):
        print(line, file=sys.stderr)
    return 1 if any(st["error"] for st in stats.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
