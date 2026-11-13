import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import router  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 11, 13, 11, 0)  # 2 hours after the inventory snapshot


class RouterCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.queue = router.ActionQueue(Path(self.tmp.name) / "actions.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def ask(self, text, now=NOW, cache=FIX):
        r = router.route(text, cache, self.queue, now)
        return r.kind, r.text


class UserExamples(RouterCase):
    """The five requests exactly as written, each answered without any AI call."""

    def test_order_with_typo_and_addressing(self):
        self.assertEqual(self.ask("피클에게 브로컬리 발주 2개 넣어줘"), ("order", "발주 접수 #1: 브로콜리 2개"))
        self.assertEqual(self.queue.view(), ["#1 접수 11:00 발주 브로콜리 2개"])

    def test_inventory(self):
        self.assertEqual(self.ask("매장에 감자튀김 재고 몇개야"), ("inventory", "감자튀김: 예상 20.0개"))

    def test_gross_sales(self):
        self.assertEqual(self.ask("지금 현재 그로스세일즈 얼마야"), (
            "sales", "2026-11-13 매장 당일 그로스 세일즈: 3,250,000원 (목표 포캐스트 400만 원 대비 81.3% 달성)"))

    def test_inbound_tomorrow(self):
        self.assertEqual(self.ask("내일 피자치즈 입고 몇개야"), ("inbound", "피자치즈: 내일(11/14) 입고 6개"))

    def test_hr_schedule_confirm(self):
        self.assertEqual(self.ask("HR 스케쥴 확정 눌러줘"), ("hr_confirm", "HR 스케줄 확정 접수 #1"))
        self.assertEqual(self.queue.view(), ["#1 접수 11:00 HR 스케줄 확정"])


class Items(RouterCase):
    def test_pizza_cheese_is_not_cheese_even_with_a_space(self):
        self.assertEqual(self.ask("피자 치즈 입고 언제야"), ("inbound", "피자치즈: 내일(11/14) 입고 6개"))
        self.assertEqual(self.ask("치즈 재고"), ("inventory", "치즈: 예상 0.0개"))

    def test_misspelling_without_an_alias(self):
        self.assertEqual(self.ask("감자튀긴 재고 몇개"), ("inventory", "감자튀김: 예상 20.0개"))

    def test_two_items_and_two_topics(self):
        self.assertEqual(self.ask("양파랑 감자튀김 재고"), ("inventory", "양파: 예상 13.0개\n감자튀김: 예상 20.0개"))
        self.assertEqual(self.ask("감자튀김 재고랑 내일 입고"),
                         ("multi", "감자튀김: 예상 20.0개\n감자튀김: 내일(11/14) 입고 10개"))

    def test_inbound_whole_day_and_none(self):
        self.assertEqual(self.ask("내일 입고 뭐 있어"),
                         ("inbound", "감자튀김: 내일(11/14) 입고 10개\n피자치즈: 내일(11/14) 입고 6개"))
        self.assertEqual(self.ask("모레 피자치즈 입고 몇개"), ("inbound", "피자치즈: 모레(11/15) 입고 없음"))
        self.assertEqual(self.ask("11/20 입고"), ("inbound", "11/20 입고 없음"))

    def test_boh(self):
        kind, text = self.ask("지금 근무 몇명이야")
        self.assertEqual(kind, "boh")
        self.assertTrue(text.startswith("[BOH 리포트 (14:05)]"))

    def test_missing_cache_says_so(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(self.ask("감자튀김 재고", cache=empty), ("inventory", "재고 데이터 없음"))


class Orders(RouterCase):
    def test_quantity_forms(self):
        self.assertEqual(self.ask("브로콜리 두 박스 발주해줘"), ("order", "발주 접수 #1: 브로콜리 2박스"))
        self.assertEqual(self.ask("발주 양파 3박스 감자튀김 2박스"),
                         ("order", "발주 접수 #2: 양파 3박스\n발주 접수 #3: 감자튀김 2박스"))
        self.assertEqual(self.ask("내일 3시까지 감자튀김 4개 발주"), ("order", "발주 접수 #4: 감자튀김 4개"))

    def test_unclear_orders_are_held_not_guessed(self):
        self.assertEqual(self.ask("발주 넣어줘"), ("held", "발주 보류: 품목을 못 찾음"))
        self.assertEqual(self.ask("브로콜리 발주 넣어줘"), ("held", "발주 보류: 브로콜리 수량을 못 찾음"))
        self.assertEqual(self.ask("양파 감자튀김 발주 2개"), ("held", "발주 보류: 품목 2개와 수량 1개가 짝이 안 맞음"))
        self.assertEqual(self.queue.items, {})

    def test_same_order_within_a_minute_is_queued_once(self):
        self.assertEqual(self.ask("브로콜리 발주 2개"), ("order", "발주 접수 #1: 브로콜리 2개"))
        self.assertEqual(self.ask("브로콜리 발주 2개", NOW + timedelta(seconds=30)),
                         ("order", "발주 접수 #1: 브로콜리 2개 (이미 접수됨)"))
        self.assertEqual(self.ask("브로콜리 발주 2개", NOW + timedelta(seconds=90)),
                         ("order", "발주 접수 #2: 브로콜리 2개"))

    def test_question_about_orders_is_not_an_order(self):
        self.assertEqual(self.ask("브로콜리 발주 몇개 했어"), ("tasks", "작업 없음"))
        self.assertEqual(self.queue.items, {})


class Queue(RouterCase):
    def test_status_updates_and_listing(self):
        self.ask("브로콜리 발주 2개")
        self.ask("HR 스케줄 확정해줘")
        self.assertEqual(self.ask("#1 완료"), ("status", "#1 완료 처리"))
        self.assertEqual(self.ask("2번 실패 로그인 만료"), ("status", "#2 실패 처리"))
        self.assertEqual(self.ask("#9 완료"), ("status", "#9 작업 없음"))
        self.assertEqual(self.ask("작업 확인"), ("tasks", "#1 완료 11:00 발주 브로콜리 2개\n"
                                                          "#2 실패 11:00 HR 스케줄 확정 (로그인 만료)"))

    def test_queue_survives_a_restart(self):
        self.ask("브로콜리 발주 2개")
        again = router.ActionQueue(self.queue.path)
        self.assertEqual(again.view(), ["#1 접수 11:00 발주 브로콜리 2개"])
        self.assertEqual(again.add({"type": "order", "text": "발주 양파 1개"}, NOW), (2, False))


class Safety(RouterCase):
    def test_unlisted_command_is_refused_not_queued(self):
        self.assertEqual(self.ask("포스기 재부팅 해줘"), ("not_allowed", "등록 안 된 작업: 포스기 재부팅 해줘"))
        self.assertEqual(self.queue.items, {})

    def test_questions_are_not_actions(self):
        self.assertEqual(self.ask("HR 스케줄 확정됐어?")[0], "ask")
        self.assertEqual(self.ask("오늘 비 오면 손님 줄어?"), ("ask", ""))
        self.assertEqual(self.queue.items, {})

    def test_pickles_as_an_item_are_not_stripped_as_a_name(self):
        self.assertEqual(router.ADDRESS_RE.sub("", "피클 재고 몇개야", count=1), "피클 재고 몇개야")
        self.assertEqual(router.ADDRESS_RE.sub("", "피클아, 양파 재고", count=1), "양파 재고")


class Speed(RouterCase):
    def test_a_request_takes_about_a_millisecond(self):
        requests = ["매장에 감자튀김 재고 몇개야", "지금 현재 그로스세일즈 얼마야", "내일 피자치즈 입고 몇개야"]
        start = time.perf_counter()
        for _ in range(300):
            for text in requests:
                router.route(text, FIX, self.queue, NOW)
        per_request_ms = (time.perf_counter() - start) / 900 * 1000
        self.assertLess(per_request_ms, 5.0)


if __name__ == "__main__":
    unittest.main()
