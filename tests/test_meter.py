import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import meter  # noqa: E402

NOW = datetime(2026, 11, 13, 11, 0)  # November: 30 days, so the daily cap is $5 / 30
PRICES = {"openai": (0.25, 2.00), "anthropic": (4.0, 20.0)}


class MeterCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "usage.jsonl"
        self.alerts = []

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, budget=5.0):
        return meter.Meter(self.path, monthly_budget=budget, clock=lambda: NOW, alert=self.alerts.append, prices=PRICES)


class Spend(MeterCase):
    def test_cost_per_call_and_persistence(self):
        m = self.make()
        self.assertAlmostEqual(m.record("openai", "gpt-5-mini", 1_000_000, 0), 0.25)
        self.assertAlmostEqual(m.record("anthropic", "claude-opus-5-5", 1000, 1000), 0.024)
        self.assertAlmostEqual(m.record("anthropic", "claude-opus-5-5:fast", 1000, 1000), 0.048)
        again = self.make()  # a restart reads the same file
        self.assertAlmostEqual(again.spent("openai", day=NOW.date()), 0.25)
        self.assertAlmostEqual(again.spent("anthropic", month=(2026, 11)), 0.072)
        self.assertAlmostEqual(again.cap(NOW.date()), 5 / 30)

    def test_alerts_fire_once_and_gpt_stops_at_the_daily_cap(self):
        m = self.make()
        cap = m.cap(NOW.date())
        tokens_for = lambda usd: int(usd / 0.25 * 1_000_000)  # noqa: E731
        m.record("openai", "gpt-5-mini", tokens_for(0.7 * cap), 0)
        self.assertEqual(self.alerts, [])
        self.assertFalse(m.blocked())
        m.record("openai", "gpt-5-mini", tokens_for(0.15 * cap), 0)  # 85%
        m.record("openai", "gpt-5-mini", 10, 0)  # still 85%: no second alert
        self.assertEqual(len(self.alerts), 1)
        self.assertTrue(self.alerts[0].startswith("OpenAI 비용 80%: 오늘 $0.142 / 일일 한도 $0.167 (월 $5)"))
        m.record("openai", "gpt-5-mini", tokens_for(0.2 * cap), 0)  # 105%
        self.assertTrue(m.blocked())
        self.assertFalse(m.blocked("anthropic"))
        self.assertEqual(len(self.alerts), 2)
        self.assertIn("오늘 한도 도달", self.alerts[1])
        self.assertIn("Claude로 넘김", self.alerts[1])

    def test_month_budget_alert(self):
        m = self.make(budget=0.5)
        m.record("openai", "gpt-5-mini", 1_700_000, 0)  # $0.425 = 85% of the month
        self.assertTrue(any(a.startswith("OpenAI 이번 달 80%: $0.42 / $0.5") for a in self.alerts))


class Weekly(unittest.TestCase):
    def test_summary_counts_times_failures_and_spend(self):
        records = [
            {"at": "2026-11-09T10:00:00", "상태": "완료", "route": "hub", "kind": "inventory", "seconds": 0.002},
            {"at": "2026-11-10T10:00:00", "상태": "완료", "route": "hub", "kind": "sales", "seconds": 0.004},
            {"at": "2026-11-10T11:00:00", "상태": "완료", "route": "hub", "kind": "order", "seconds": 0.003},
            {"at": "2026-11-11T09:00:00", "id": "Q-20261111-001", "상태": "대기"},
            {"at": "2026-11-11T09:00:03", "id": "Q-20261111-001", "상태": "완료", "answer": "결론: x", "seconds": 3.0,
             "missing": ["GPT"], "rejected": []},
            {"at": "2026-11-12T09:00:05", "id": "Q-20261112-001", "상태": "완료", "answer": "결론: 모름\n근거: …",
             "seconds": 5.0, "missing": [], "rejected": ["Claude"]},
            {"at": "2026-11-12T10:00:00", "id": "Q-20261112-002", "상태": "완료", "answer": "결론: x", "seconds": 0.0,
             "cached": True},
            {"at": "2026-11-16T09:00:00", "상태": "완료", "route": "hub", "kind": "inventory", "seconds": 1},  # next week
        ]
        usage = [{"at": "2026-11-11T09:00:03", "provider": "openai", "usd": 0.0123},
                 {"at": "2026-11-12T09:00:05", "provider": "anthropic", "usd": 0.3}]
        self.assertEqual(meter.weekly_summary(records, usage, date(2026, 11, 9)), "\n".join([
            "## [주간 요약] 11/9~11/15",
            "요청 6건: 데이터 2, 지시 1, AI 3 (캐시 1)",
            "평균 응답: 데이터 0.003초, AI 4.0초",
            "실패 3건: 응답 없음 1 (GPT 1), 반려 1, 모름 1, AI 연결 안 됨 0",
            "비용: OpenAI $0.01, Claude $0.30",
        ]))


if __name__ == "__main__":
    unittest.main()
