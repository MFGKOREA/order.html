import importlib.util
import io
import json
import os
import sys
import threading
import time
import unittest
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import ai_board as ab  # noqa: E402
import pickle_relay as pr  # noqa: E402

NOW = datetime(2026, 11, 13, 14, 5)
BOARD = """회의 메모 (무시됨)
## 질문: [2026-11-13 09:00] 어제 질문
- 대상: Claude, 그록봇, GPT, 피클(루이)
- 속도 기준: 단일 3초 내, 2중 전달 10초 안쪽 완료
[Claude] 답변: 예전 답
[GPT] 답변: 예전 답
[레미] 답변: 예전 답
## 질문: [2026-11-13 14:05] 오늘 양파 발주량?
- 대상: Claude, 그록봇, GPT, 피클(루이)
- 속도 기준: 단일 3초 내, 2중 전달 10초 안쪽 완료
[Claude] 답변: 안녕하세요!
결론: 양파 20kg 발주
[GPT] 답변:
[레미] 답변:
"""


def timed(*steps):
    """Fake AI: steps are lines to yield or float seconds to wait."""
    def asker(question, system):
        for step in steps:
            if isinstance(step, float):
                time.sleep(step)
            else:
                yield step
    return asker


class Board(unittest.TestCase):
    def test_post_has_slots_and_valid_header(self):
        text = ab.post("오늘 양파 발주량?", NOW)
        self.assertEqual(pr.lint("\n".join(text.splitlines()[:3]), "question"), [])
        self.assertEqual(text.splitlines()[3:], ["[Claude] 답변:", "[GPT] 답변:", "[레미] 답변:"])

    def test_post_round_trips(self):
        text = ab.post("오늘 양파 발주량?", NOW)
        self.assertEqual(ab.render(ab.parse(text)[0]), text)

    def test_parse_takes_latest_question_and_multiline_answers(self):
        blocks = ab.parse(BOARD)
        self.assertEqual(len(blocks), 2)
        last = blocks[-1]
        self.assertEqual(last["question"], "오늘 양파 발주량?")
        self.assertEqual(last["answers"], {"Claude": "안녕하세요!\n결론: 양파 20kg 발주", "GPT": "", "레미": ""})

    def test_fill_only_empty_auto_slots_and_leaves_remy_blank(self):
        block = ab.parse(BOARD)[-1]
        calls = []

        def gpt(q, system):
            calls.append(q)
            yield "양파 20kg 발주"

        def claude(q, system):
            calls.append("claude must not be asked: its slot is already answered")
            return iter(())

        stats = ab.fill(block, {"Claude": claude, "GPT": gpt})
        self.assertEqual(calls, ["오늘 양파 발주량?"])
        self.assertEqual(block["answers"]["GPT"], "양파 20kg 발주")
        self.assertEqual(block["answers"]["레미"], "")
        self.assertEqual(list(stats), ["GPT"])

    def test_fill_streams_each_useful_line_the_moment_it_arrives(self):
        block = ab.parse(ab.post("q", NOW))[0]
        events, start = [], time.perf_counter()
        askers = {"Claude": timed("안녕하세요", 0.4, "A"),
                  "GPT": timed(0.1, "B", 0.4, "C")}
        stats = ab.fill(block, askers, on_line=lambda s, l: events.append((s, l, time.perf_counter() - start)))
        self.assertEqual([(s, l) for s, l, _ in events], [("GPT", "B"), ("Claude", "A"), ("GPT", "C")])
        self.assertLess(events[0][2], 0.3)  # fastest AI reaches Pickle first, not after the slowest
        self.assertLess(stats["GPT"]["first"], stats["Claude"]["first"])
        self.assertGreaterEqual(stats["GPT"]["done"], 0.5)
        self.assertEqual(block["answers"], {"Claude": "안녕하세요\nA", "GPT": "B\nC", "레미": ""})

    def test_fill_runs_in_parallel_and_drops_partial_answer_on_error(self):
        block = ab.parse(ab.post("q", NOW))[0]

        def broken(q, system):
            yield "부분"
            raise ConnectionError("no route")

        start = time.perf_counter()
        stats = ab.fill(block, {"Claude": timed(0.3, "ok"), "GPT": broken})
        self.assertLess(time.perf_counter() - start, 0.5)
        self.assertIsNone(stats["Claude"]["error"])
        self.assertIn("ConnectionError", stats["GPT"]["error"])
        self.assertEqual(block["answers"]["GPT"], "")

    def test_relay_strips_filler_dedupes_and_withholds_banned_lines(self):
        block = ab.parse(BOARD)[-1]
        block["answers"]["GPT"] = "양파 20kg 발주\n관제 센터 확인\n감사합니다"
        msg, withheld = ab.relay(block)
        self.assertEqual(msg, "양파 20kg 발주")
        self.assertEqual(withheld, ["관제 센터 확인"])

    def test_speed_report(self):
        stats = {"Claude": {"first": 1.2, "done": 1.5, "error": None},
                 "GPT": {"first": 3.5, "done": 3.6, "error": None}}
        self.assertEqual(ab.speed_report(stats, 3.62), [
            "Claude: first line 1.20s OK, done 1.50s",
            "GPT: first line 3.50s OVER 3s, done 3.60s",
            "first to Pickle: 1.20s",
            "total: 3.62s OK",
        ])

    def test_run_ask_sends_pickle_lines_before_the_board_block(self):
        out, err = io.StringIO(), io.StringIO()
        askers = {"Claude": timed(0.2, "양파 20kg 발주", "관제 기록"), "GPT": timed("양파 20kg 발주", 0.1, "예약 4개")}
        self.assertEqual(ab.run_ask("오늘 양파 발주량?", askers, out, err), 0)
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[:3], ["양파 20kg 발주", "예약 4개", "---"])
        self.assertTrue(lines[3].startswith("## 질문: "))
        self.assertIn("WITHHELD (banned word 관제): 관제 기록", err.getvalue())
        self.assertIn("first to Pickle:", err.getvalue())

    def test_serve_warms_up_then_answers_every_line(self):
        out, err = io.StringIO(), io.StringIO()

        def no_key():
            raise PermissionError("no key")

        ab.serve({"Claude": timed("A"), "GPT": timed("B")}, {"Claude": lambda: None, "GPT": no_key},
                 inp=io.StringIO("q1\n\nq2\n"), out=out, err=err)
        self.assertIn("warm Claude: OK", err.getvalue())
        self.assertIn("warm GPT: PermissionError: no key", err.getvalue())
        self.assertEqual(out.getvalue().count("## 질문: "), 2)


class _Mock(BaseHTTPRequestHandler):
    """Local stand-in for both APIs. Streams in each provider's SSE format."""
    seen = []
    tail = 0.0  # seconds between the first line and the rest of an answer
    busy_fast = False  # answer fast-mode Claude requests with 429

    def _json(self, status, obj):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        _Mock.seen.append(("GET", self.path, {k.lower(): v for k, v in self.headers.items()}, None))
        if self.path.startswith("/v1/models"):
            self._json(200, {"data": [], "has_more": False, "first_id": None, "last_id": None, "object": "list"})
        else:
            self._json(404, {})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Mock.seen.append(("POST", self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        if self.path.startswith("/v1/messages"):
            if body.get("speed") == "fast" and _Mock.busy_fast:
                return self._json(429, {"type": "error", "error": {"type": "rate_limit_error", "message": "busy"}})
            events = self._anthropic(body)
        else:
            events = self._openai(body)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        try:
            for ev in events:
                if ev is None:
                    time.sleep(_Mock.tail)
                    continue
                self.wfile.write(ev.encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    @staticmethod
    def _anthropic(body):
        def ev(name, data):
            return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        refuse = body["messages"][0]["content"] == "REFUSE"
        texts = [] if refuse else ["안녕하세요\n양파 20kg 발주\n", None, "추가 설명"]
        yield ev("message_start", {"type": "message_start", "message": {
            "id": "msg_1", "type": "message", "role": "assistant", "model": body["model"], "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 0}}})
        yield ev("content_block_start", {"type": "content_block_start", "index": 0,
                                         "content_block": {"type": "text", "text": ""}})
        for t in texts:
            yield None if t is None else ev("content_block_delta", {
                "type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": t}})
        yield ev("content_block_stop", {"type": "content_block_stop", "index": 0})
        delta = {"stop_reason": "refusal" if refuse else "end_turn", "stop_sequence": None}
        if refuse:
            delta["stop_details"] = {"type": "refusal", "category": None, "explanation": None}
        yield ev("message_delta", {"type": "message_delta", "delta": delta, "usage": {"output_tokens": 5}})
        yield ev("message_stop", {"type": "message_stop"})

    @staticmethod
    def _openai(body):
        def chunk(delta, finish=None):
            data = {"id": "c1", "object": "chat.completion.chunk", "created": 0, "model": body["model"],
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
            return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        yield chunk({"role": "assistant", "content": "양파 20kg 발주\n"})
        yield None
        yield chunk({"content": "추가 설명"})
        yield chunk({}, "stop")
        yield "data: [DONE]\n\n"

    def log_message(self, *args):
        pass


def _has(module):
    return importlib.util.find_spec(module) is not None


@unittest.skipUnless(_has("anthropic") and _has("openai"), "pip install -r requirements.txt")
class WireFormat(unittest.TestCase):
    """Real SDK calls against the local mock: exact requests, streaming, fallback paths (no real keys)."""

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Mock)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{cls.server.server_port}"
        env = {"ANTHROPIC_BASE_URL": base, "ANTHROPIC_API_KEY": "test-key",
               "OPENAI_BASE_URL": base + "/v1", "OPENAI_API_KEY": "test-key"}
        cls.saved = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        import ask_claude
        import ask_gpt
        cls.claude, cls.gpt = ask_claude, ask_gpt

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        for k, v in cls.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        cls.claude._client = cls.gpt._client = None

    def setUp(self):
        _Mock.seen.clear()
        _Mock.tail, _Mock.busy_fast = 0.0, False
        self.claude._client = self.gpt._client = None  # fresh clients bound to the mock

    def posts(self):
        return [(path, headers, body) for method, path, headers, body in _Mock.seen if method == "POST"]

    def first_line_and_done(self, slot, asker):
        block = ab.parse(ab.post("오늘 양파 발주량?", NOW))[0]
        stats = ab.fill(block, {slot: asker})
        return stats[slot], block

    def test_claude_request_and_streaming(self):
        _Mock.tail = 0.8
        st, block = self.first_line_and_done("Claude", self.claude.lines)
        self.assertIsNone(st["error"])
        self.assertLess(st["first"], 0.5)  # first useful line arrives before the slow tail
        self.assertGreaterEqual(st["done"], 0.8)
        self.assertEqual(block["answers"]["Claude"], "안녕하세요\n양파 20kg 발주\n추가 설명")
        path, headers, body = self.posts()[0]
        self.assertTrue(path.startswith("/v1/messages"))
        self.assertEqual(headers["authorization"], "Bearer test-key")  # SDK 2.x sends keys as Bearer
        self.assertIn("server-side-fallback-2026-07-01", headers["anthropic-beta"])
        self.assertNotIn("fast-mode", headers["anthropic-beta"])
        self.assertEqual((body["model"], body["stream"], body["fallbacks"]), ("claude-opus-5-5", True, "default"))
        self.assertEqual(body["output_config"], {"effort": "low"})
        self.assertEqual(body["system"], ab.SYSTEM)
        self.assertNotIn("speed", body)
        self.assertNotIn("thinking", body)

    def test_claude_fast_mode_and_fallback_to_standard_when_busy(self):
        self.claude.FAST, _Mock.busy_fast = True, True
        try:
            self.assertEqual(list(self.claude.lines("q", ab.SYSTEM)), ["안녕하세요", "양파 20kg 발주", "추가 설명"])
        finally:
            self.claude.FAST = False
        (_, h1, b1), (_, h2, b2) = self.posts()
        self.assertEqual(b1["speed"], "fast")
        self.assertIn("fast-mode-2026-02-01", h1["anthropic-beta"])
        self.assertNotIn("speed", b2)  # retried once at standard speed
        self.assertNotIn("fast-mode", h2["anthropic-beta"])

    def test_claude_whole_chain_refusal_raises(self):
        with self.assertRaisesRegex(RuntimeError, "declined"):
            list(self.claude.lines("REFUSE", ab.SYSTEM))

    def test_gpt_request_and_streaming(self):
        _Mock.tail = 0.8
        st, block = self.first_line_and_done("GPT", self.gpt.lines)
        self.assertIsNone(st["error"])
        self.assertLess(st["first"], 0.5)
        self.assertEqual(block["answers"]["GPT"], "양파 20kg 발주\n추가 설명")
        path, headers, body = self.posts()[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(headers["authorization"], "Bearer test-key")
        self.assertEqual((body["model"], body["stream"], body["reasoning_effort"]), ("gpt-5-mini", True, "minimal"))
        self.assertEqual(body["messages"][0], {"role": "system", "content": ab.SYSTEM})
        self.assertNotIn("service_tier", body)

    def test_gpt_priority_tier(self):
        self.gpt.PRIORITY = True
        try:
            list(self.gpt.lines("q", ab.SYSTEM))
        finally:
            self.gpt.PRIORITY = False
        self.assertEqual(self.posts()[0][2]["service_tier"], "priority")

    def test_serve_end_to_end(self):
        out, err = io.StringIO(), io.StringIO()
        askers, warmers = ab.load_ais()
        ab.serve(askers, warmers, inp=io.StringIO("오늘 양파 발주량?\n"), out=out, err=err)
        gets = [p for m, p, _, _ in _Mock.seen if m == "GET"]
        self.assertEqual(len(gets), 2)  # both connections opened before the first question
        self.assertIn("warm Claude: OK", err.getvalue())
        self.assertIn("warm GPT: OK", err.getvalue())
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[:3], ["양파 20kg 발주", "추가 설명", "---"])  # same line from both AIs sent once


if __name__ == "__main__":
    unittest.main()
