"""OpenAI-only setup: Claude skipped, GPT takes its work, judgment questions go to GPT, call cap, 게시판."""
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import ai_board  # noqa: E402
import hub  # noqa: E402
import meter  # noqa: E402
import pipeline as pl  # noqa: E402
import router  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 11, 13, 14, 30)
ANSWER = "결론: 금요일\n근거: 런치 세트 20% 할인 (매장 11/13 09:00)\n확인 필요: 없음"


def _has(module):
    import importlib.util
    return importlib.util.find_spec(module) is not None


class GptOnly(unittest.TestCase):
    @unittest.skipUnless(_has("openai"), "pip install -r requirements.txt")
    def test_only_the_ai_with_a_key_is_loaded(self):
        askers, warmers = ai_board.load_ais({"OPENAI_API_KEY": "x"})
        self.assertEqual((list(askers), list(warmers)), (["GPT"], ["GPT"]))

    def test_judgment_question_goes_to_ai_lookup_stays(self):
        with tempfile.TemporaryDirectory() as d:
            q = router.ActionQueue(Path(d) / "a.jsonl")
            self.assertEqual(router.route("이번 주 행사 중에 손님 많을 날은?", FIX, q, NOW).kind, "ask")
            self.assertEqual(router.route("이번 주 행사 뭐야", FIX, q, NOW).kind, "promotions")
            self.assertEqual(router.route("매장에 감자튀김 재고 몇개야", FIX, q, NOW).kind, "inventory")

    def test_gpt_answers_claude_work_without_checking_itself(self):
        seen = []

        def gpt(message, system):
            seen.append(message)
            yield from ANSWER.splitlines()

        with tempfile.TemporaryDirectory() as d:
            p = pl.Pipeline(FIX, {"GPT": gpt}, systems={"GPT": "G"}, board=pl.Board(Path(d) / "b.txt"),
                            clock=lambda: NOW)
            out = []
            rec = p.run("다음 주 화요일 양파 발주량?", out.append)  # analysis: Claude's kind
            self.assertEqual(rec["targets"], ["GPT"])
            self.assertEqual(len(seen), 1)
            self.assertTrue(out[0].startswith("결론: 금요일"))

    def test_daily_call_cap(self):
        with tempfile.TemporaryDirectory() as d:
            m = meter.Meter(Path(d) / "u.jsonl", clock=lambda: NOW)
            for _ in range(meter.DAILY_CALLS):
                m.record("openai", "gpt-4o-mini", 1, 1)
            self.assertTrue(m.blocked("openai"))

    def test_board_answers_open_remy_questions(self):
        with tempfile.TemporaryDirectory() as d:
            drive = Path(d)
            (drive / "게시판.txt").write_text(
                "## [대기] Q-20261113-001 14:00 세콤 화면 봐줘 → 레미\n"
                "## [대기] Q-20261113-002 14:01 HR 확인 → 레미\n[완료] Q-20261113-002\n", encoding="utf-8")
            lines = hub.answer_board(drive, FIX, lambda m, s: iter(ANSWER.splitlines()), NOW, system="G")
            self.assertEqual(len(lines), 1)
            self.assertTrue(lines[0].startswith("Q-20261113-001 답: 결론: 금요일 / 근거: "))
            self.assertRegex(lines[0], pl.REMY_RE)
            self.assertIn(lines[0], (drive / "요청.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
