"""
Gateway tests with FAKE providers: no API key, no internet, no waiting.
Each fake provider follows a "script": a list of what to do on each call
("ok", "timeout", "rate_limit", "bad_key").
"""

import pytest

from app.llm.gateway import AllProvidersFailed, BudgetExceeded, LLMGateway
from app.llm.providers import LLMResult, ProviderError


class FakeProvider:
    def __init__(self, name, script, model=None):
        self.name = name
        self.model = model or f"{name}-model"
        self.script = list(script)
        self.calls = 0

    def generate(self, messages, max_tokens=512, timeout=20.0):
        self.calls += 1
        step = self.script.pop(0) if self.script else "ok"
        if step == "timeout":
            raise ProviderError(f"{self.name} timed out", retryable=True)
        if step == "rate_limit":
            raise ProviderError(f"{self.name} returned HTTP 429", retryable=True)
        if step == "bad_key":
            raise ProviderError(f"{self.name} returned HTTP 401", retryable=False)
        return LLMResult(text=f"hello from {self.name}", provider=self.name, model=self.model,
                         input_tokens=100, output_tokens=50)


def make_gateway(providers, spent=0.0, budget=1.0, prices=None, **kwargs):
    log = []
    gw = LLMGateway(
        providers=providers,
        prices=prices or {},
        log_call=lambda **row: log.append(row),
        spent_today=lambda: spent,
        daily_budget_usd=budget,
        sleep=lambda s: None,          # don't really wait during tests
        **kwargs,
    )
    return gw, log


MSG = [{"role": "user", "content": "hi"}]


def test_first_provider_answers():
    main, backup = FakeProvider("gemini", ["ok"]), FakeProvider("ollama", ["ok"])
    gw, log = make_gateway([main, backup])
    r = gw.chat(MSG)
    assert r.provider == "gemini" and r.attempts == 1
    assert backup.calls == 0                      # backup never needed
    assert log[0]["status"] == "ok"


def test_retry_then_success_on_same_provider():
    main = FakeProvider("gemini", ["timeout", "ok"])
    gw, log = make_gateway([main, FakeProvider("ollama", [])])
    r = gw.chat(MSG)
    assert r.provider == "gemini" and r.attempts == 2
    assert [row["status"] for row in log] == ["error", "ok"]


def test_failover_after_retries_run_out():
    main = FakeProvider("gemini", ["rate_limit", "rate_limit", "rate_limit"])
    backup = FakeProvider("ollama", ["ok"])
    gw, log = make_gateway([main, backup], max_retries=2)
    r = gw.chat(MSG)
    assert r.provider == "ollama"
    assert main.calls == 3                        # 1 try + 2 retries
    assert r.attempts == 4


def test_non_retryable_error_fails_over_immediately():
    main = FakeProvider("gemini", ["bad_key"])
    backup = FakeProvider("ollama", ["ok"])
    gw, _ = make_gateway([main, backup], max_retries=2)
    r = gw.chat(MSG)
    assert r.provider == "ollama"
    assert main.calls == 1                        # a bad key won't fix itself: no retries


def test_all_providers_fail():
    gw, log = make_gateway([FakeProvider("gemini", ["bad_key"]), FakeProvider("ollama", ["bad_key"])])
    with pytest.raises(AllProvidersFailed):
        gw.chat(MSG)
    assert len(log) == 2 and all(row["status"] == "error" for row in log)


def test_circuit_breaker_skips_a_broken_provider():
    main = FakeProvider("gemini", ["bad_key"] * 10)
    backup = FakeProvider("ollama", [])
    gw, _ = make_gateway([main, backup], max_retries=0)
    for _ in range(3):                            # 3 failures in a row -> circuit opens
        gw.chat(MSG)
    calls_before = main.calls
    r = gw.chat(MSG)
    assert r.provider == "ollama"
    assert main.calls == calls_before             # gemini was skipped, not called


def test_budget_guard_stops_spending():
    gw, _ = make_gateway([FakeProvider("gemini", ["ok"])], spent=1.5, budget=1.0)
    with pytest.raises(BudgetExceeded):
        gw.chat(MSG)


def test_cost_is_calculated_from_tokens():
    prices = {"paid-model": (2.0, 8.0)}            # USD per 1M input / output tokens
    gw, log = make_gateway([FakeProvider("gemini", ["ok"], model="paid-model")], prices=prices)
    r = gw.chat(MSG)
    # 100 input tokens * 2 / 1M + 50 output tokens * 8 / 1M = 0.0002 + 0.0004
    assert r.cost_usd == pytest.approx(0.0006)
    assert log[0]["cost_usd"] == pytest.approx(0.0006)
