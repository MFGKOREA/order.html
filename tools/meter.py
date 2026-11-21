"""API spend and the weekly summary. Stdlib only.

Prices are USD per million tokens, set with GPT_PRICE_IN / GPT_PRICE_OUT and CLAUDE_PRICE_IN /
CLAUDE_PRICE_OUT. Defaults: gpt-5-mini 0.25 / 2.00 and claude-sonnet-5-5 3 / 15 (check the current
prices); Opus models and gpt-4o-mini use MODEL_PRICES; fast mode costs double.

One budget covers Claude and GPT together: HUB_MONTHLY_BUDGET (default $30) becomes a daily cap,
budget ÷ days in the month, counted over both providers. At 80% of the day's cap, or of the month's
budget, 신우님 gets an alert; at 100% of the day's cap both AIs stop for the day (data answers keep
working). GPT also stops after GPT_DAILY_CALLS answers a day (default 200).
"""
import calendar
import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path


def _env(name, default):
    return float(os.environ.get(name, default))


# Per-model prices (USD per million tokens) that differ from the provider default.
MODEL_PRICES = {"gpt-4o-mini": (0.15, 0.60), "claude-opus-5-5": (4.0, 20.0), "claude-opus-5": (4.0, 20.0),
                "claude-opus-4-8": (4.0, 20.0)}
PROVIDERS = ("openai", "anthropic")
DAILY_CALLS = int(os.environ.get("GPT_DAILY_CALLS", "200"))  # OpenAI answers per day, then GPT stops


def default_prices():
    return {"openai": (_env("GPT_PRICE_IN", 0.25), _env("GPT_PRICE_OUT", 2.00)),
            "anthropic": (_env("CLAUDE_PRICE_IN", 3.0), _env("CLAUDE_PRICE_OUT", 15.0))}


class Meter:
    """Spend per call in <state>/usage.jsonl; daily and monthly totals; one cap for Claude + GPT."""

    def __init__(self, path, monthly_budget=None, clock=datetime.now, alert=None, prices=None):
        self.path, self.clock, self.alert = Path(path), clock, alert or (lambda message: None)
        self.budget = _env("HUB_MONTHLY_BUDGET", 30.0) if monthly_budget is None else monthly_budget
        self.prices = prices or default_prices()
        self.lock, self.alerted = threading.Lock(), set()
        self.records = self._read()

    def _read(self):
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        out = []
        for line in lines:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return out

    def cap(self, day):
        """The daily cap (Claude + GPT): the month's budget spread over its days."""
        return self.budget / calendar.monthrange(day.year, day.month)[1]

    def spent(self, provider, day=None, month=None):
        """USD spent by a provider on a day (date) or in a month ((year, month))."""
        total = 0.0
        for r in self.records:
            at = datetime.fromisoformat(r["at"])
            if r["provider"] == provider and (day is None or at.date() == day) and \
                    (month is None or (at.year, at.month) == month):
                total += r["usd"]
        return total

    def record(self, provider, model, input_tokens, output_tokens):
        """One answer's usage. Returns its cost in USD."""
        p_in, p_out = self.prices[provider]
        base = model.removesuffix(":fast")
        own = "GPT_PRICE_IN" if provider == "openai" else "CLAUDE_PRICE_IN"
        if base in MODEL_PRICES and not os.environ.get(own):
            p_in, p_out = MODEL_PRICES[base]
        usd = (input_tokens * p_in + output_tokens * p_out) / 1_000_000
        if model.endswith(":fast"):
            usd *= 2
        now = self.clock()
        rec = {"at": now.isoformat(timespec="seconds"), "provider": provider, "model": model,
               "in": input_tokens, "out": output_tokens, "usd": round(usd, 6)}
        with self.lock:
            self.records.append(rec)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        self._check(now.date())
        return usd

    def total(self, day=None, month=None):
        """USD spent by Claude and GPT together."""
        return sum(self.spent(p, day=day, month=month) for p in PROVIDERS)

    def _check(self, day):
        today, cap = self.total(day=day), self.cap(day)
        month = self.total(month=(day.year, day.month))
        checks = [  # highest level first; once a level fires, the lower one of the same span is done too
            ((day.isoformat(), 1.0), today >= cap,
             f"AI 오늘 한도 도달 (${today:.3f} / ${cap:.3f}): Claude·GPT를 내일까지 멈춤"),
            ((day.isoformat(), 0.8), today >= 0.8 * cap,
             f"AI 비용 80%: 오늘 ${today:.3f} / 일일 한도 ${cap:.3f} (월 ${self.budget:g})"),
            ((f"{day:%Y-%m}", 0.8), month >= 0.8 * self.budget,
             f"AI 이번 달 80%: ${month:.2f} / ${self.budget:g}"),
        ]
        with self.lock:
            fire = []
            for key, crossed, message in checks:
                if crossed and key not in self.alerted:
                    self.alerted.add(key)
                    if key[1] == 1.0:
                        self.alerted.add((key[0], 0.8))
                    fire.append(message)
        for message in fire:
            self.alert(message)

    def calls(self, provider, day):
        return sum(1 for r in self.records
                   if r["provider"] == provider and datetime.fromisoformat(r["at"]).date() == day)

    def blocked(self, provider="openai"):
        """True once today's Claude + GPT spend reaches the daily cap; GPT also after DAILY_CALLS answers."""
        if provider not in PROVIDERS:
            return False
        day = self.clock().date()
        if self.total(day=day) >= self.cap(day):
            return True
        return provider == "openai" and self.calls("openai", day) >= DAILY_CALLS

    def status_line(self, day):
        return f"AI 오늘 ${self.total(day=day):.2f} / ${self.cap(day):.2f}, 이번 달 ${self.total(month=(day.year, day.month)):.2f} / ${self.budget:g}"


DATA_KINDS = {"inventory", "inbound", "sales", "boh", "multi", "tasks", "roster", "promotions"}
ACTION_KINDS = {"order", "hr_confirm", "held", "not_allowed"}


def weekly_summary(records, usage, monday):
    """One Monday–Sunday week from envelopes.jsonl and usage.jsonl records, as board lines."""
    end = monday + timedelta(days=7)

    def in_week(r):
        return monday <= datetime.fromisoformat(r["at"]).date() < end

    done = [r for r in records if r.get("상태") == "완료" and in_week(r)]
    hub = [r for r in done if r.get("route") == "hub"]
    data = [r for r in hub if r.get("kind") in DATA_KINDS]
    actions = [r for r in hub if r.get("kind") in ACTION_KINDS]
    ai = [r for r in done if r.get("route") != "hub"]
    cached = [r for r in ai if r.get("cached")]
    asked = [r for r in ai if not r.get("cached")]

    def avg(rs):
        return sum(r.get("seconds", 0) for r in rs) / len(rs) if rs else 0.0

    missing = [s for r in ai for s in r.get("missing", [])]
    rejected = [s for r in ai for s in r.get("rejected", [])]
    unknown = [r for r in ai if r.get("answer", "").startswith("결론: 모름")]
    no_ai = [r for r in ai if r.get("answer") == "AI 연결 안 됨"]
    by_ai = ", ".join(f"{name} {missing.count(name)}" for name in sorted(set(missing)))
    spend = {p: sum(u["usd"] for u in usage if u["provider"] == p and in_week(u)) for p in ("openai", "anthropic")}
    sunday = end - timedelta(days=1)
    failures = len(missing) + len(rejected) + len(unknown) + len(no_ai)
    return "\n".join([
        f"## [주간 요약] {monday.month}/{monday.day}~{sunday.month}/{sunday.day}",
        f"요청 {len(done)}건: 데이터 {len(data)}, 지시 {len(actions)}, AI {len(ai)} (캐시 {len(cached)})",
        f"평균 응답: 데이터 {avg(data):.3f}초, AI {avg(asked):.1f}초",
        f"실패 {failures}건: 응답 없음 {len(missing)}" + (f" ({by_ai})" if by_ai else "")
        + f", 반려 {len(rejected)}, 모름 {len(unknown)}, AI 연결 안 됨 {len(no_ai)}",
        f"비용: OpenAI ${spend['openai']:.2f}, Claude ${spend['anthropic']:.2f}",
    ])
