import importlib.util
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
            return "양파 20kg 발주"

        def claude(q, system):
            raise AssertionError("Claude slot already answered; must not be asked again")

        timings = ab.fill(block, {"Claude": claude, "GPT": gpt})
        self.assertEqual(calls, ["오늘 양파 발주량?"])
        self.assertEqual(block["answers"]["GPT"], "양파 20kg 발주")
        self.assertEqual(block["answers"]["레미"], "")
        self.assertEqual(list(timings), ["GPT"])

    def test_fill_runs_in_parallel_and_reports_errors(self):
        block = ab.parse(ab.post("q", NOW))[0]

        def slow(q, system):
            time.sleep(0.3)
            return "ok"

        def broken(q, system):
            raise ConnectionError("no route")

        start = time.perf_counter()
        timings = ab.fill(block, {"Claude": slow, "GPT": broken})
        self.assertLess(time.perf_counter() - start, 0.5)  # parallel, not 0.3 + retries
        self.assertIsNone(timings["Claude"][1])
        self.assertIn("ConnectionError", timings["GPT"][1])
        self.assertEqual(block["answers"]["GPT"], "")

    def test_relay_strips_filler_dedupes_and_skips_empty(self):
        block = ab.parse(BOARD)[-1]
        block["answers"]["GPT"] = "양파 20kg 발주\n감사합니다"
        msg, errors = ab.relay(block)
        self.assertEqual(msg, "양파 20kg 발주")
        self.assertEqual(errors, [])

    def test_speed_report(self):
        report = ab.speed_report({"Claude": (1.2, None), "GPT": (3.5, None)}, 3.6)
        self.assertEqual(report, ["Claude: 1.20s OK", "GPT: 3.50s OVER 3s", "total: 3.60s OK"])


class _Mock(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Mock.seen.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        if self.path.startswith("/v1/messages"):
            reply = {"id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
                     "content": [{"type": "text", "text": "양파 20kg 발주"}], "stop_reason": "end_turn",
                     "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}}
        else:
            reply = {"id": "c1", "object": "chat.completion", "created": 0, "model": body["model"],
                     "choices": [{"index": 0, "finish_reason": "stop",
                                  "message": {"role": "assistant", "content": "양파 20kg 발주"}}],
                     "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def _has(module):
    return importlib.util.find_spec(module) is not None


@unittest.skipUnless(_has("anthropic") and _has("openai"), "pip install -r requirements.txt")
class WireFormat(unittest.TestCase):
    """Checks the exact requests both SDK calls send, against a local mock server (no real keys)."""

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Mock)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.env = {"ANTHROPIC_BASE_URL": base, "ANTHROPIC_API_KEY": "test-key",
                   "OPENAI_BASE_URL": base + "/v1", "OPENAI_API_KEY": "test-key"}
        cls.saved = {k: os.environ.get(k) for k in cls.env}
        os.environ.update(cls.env)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        for k, v in cls.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def setUp(self):
        _Mock.seen.clear()

    def test_claude_request(self):
        import ask_claude
        self.assertEqual(ask_claude.ask("오늘 양파 발주량?", ab.SYSTEM), "양파 20kg 발주")
        path, headers, body = _Mock.seen[0]
        self.assertTrue(path.startswith("/v1/messages"))
        self.assertEqual(headers["authorization"], "Bearer test-key")  # SDK 2.x sends keys as Bearer
        self.assertIn("server-side-fallback-2026-07-01", headers["anthropic-beta"])
        self.assertEqual(body["model"], "claude-opus-5-5")
        self.assertEqual(body["fallbacks"], "default")
        self.assertEqual(body["output_config"], {"effort": "low"})
        self.assertEqual(body["system"], ab.SYSTEM)
        self.assertNotIn("thinking", body)

    def test_gpt_request(self):
        import ask_gpt
        self.assertEqual(ask_gpt.ask("오늘 양파 발주량?", ab.SYSTEM), "양파 20kg 발주")
        path, headers, body = _Mock.seen[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(headers["authorization"], "Bearer test-key")
        self.assertEqual(body["model"], "gpt-5-mini")
        self.assertEqual(body["messages"][0], {"role": "system", "content": ab.SYSTEM})

    def test_full_pipeline_through_cli(self):
        start = time.perf_counter()
        self.assertEqual(ab.main(["ask", "오늘 양파 발주량?"]), 0)
        self.assertLess(time.perf_counter() - start, ab.TOTAL_LIMIT)
        self.assertEqual(len(_Mock.seen), 2)  # Claude + GPT; 레미 is never called


if __name__ == "__main__":
    unittest.main()
