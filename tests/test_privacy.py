import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import privacy  # noqa: E402


class Patterns(unittest.TestCase):
    def setUp(self):
        self.f = privacy.Filter()

    def test_masks_personal_data(self):
        cases = {
            "연락처 010-1234-5678": ("연락처 [가림]", ["전화번호"]),
            "집 02 123 4567로": ("집 [가림]로", ["전화번호"]),
            "메일 someone@example.com 로": ("메일 [가림] 로", ["이메일"]),
            "주민 900101-1234567": ("주민 [가림]", ["주민번호"]),
            "카드 1234-5678-9012-3456": ("카드 [가림]", ["카드번호"]),
            "계좌 110-123-456789": ("계좌 [가림]", ["계좌번호"]),
            "아파트 101동 1203호": ("아파트 [가림]", ["집 주소"]),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(self.f.scrub(text), expected)

    def test_store_data_passes_untouched(self):
        for text in ("2026-11-13 매장 당일 그로스 세일즈: 3,250,000원 (목표 포캐스트 400만 원 대비 81.3% 달성)",
                     "감자튀김: 예상 20.0개", "피자치즈: 내일(11/14) 입고 6개", "#3 접수 14:05 발주 브로콜리 2개",
                     "Q-20261113-007 14:05:06", "근거: 최근 4주 화요일 소진 18~22kg (POS 11/13 14:00)",
                     "[BOH 리포트 (14:05)]\n- 근무 중: 5명"):
            with self.subTest(text=text):
                self.assertEqual(self.f.scrub(text), (text, []))


class Terms(unittest.TestCase):
    def test_terms_file_is_reread_when_it_changes(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "private_terms.txt"
            f = privacy.Filter(path)
            self.assertEqual(f.scrub("신우님 본가 강릉시 어딘가로"), ("신우님 본가 강릉시 어딘가로", []))
            path.write_text("# 개인 단어 목록\n강릉시 어딘가로\n", encoding="utf-8")
            self.assertEqual(f.scrub("신우님 본가 강릉시 어딘가로"), ("신우님 본가 [가림]", ["개인 단어"]))
            time.sleep(0.01)
            path.write_text("본가\n", encoding="utf-8")
            self.assertEqual(f.scrub("신우님 본가"), ("신우님 [가림]", ["개인 단어"]))

    def test_missing_terms_file_means_patterns_only(self):
        f = privacy.Filter("/nonexistent/private_terms.txt")
        self.assertEqual(f.scrub("010-1234-5678"), ("[가림]", ["전화번호"]))


if __name__ == "__main__":
    unittest.main()
