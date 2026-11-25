"""
The LLM gateway: one front door to several LLM providers.

For every request it:
  1. checks the daily BUDGET (stop before spending too much)
  2. tries the providers IN ORDER (e.g. Gemini first, then Ollama)
  3. for each provider:
       - skips it if its CIRCUIT BREAKER is open (it failed many times recently)
       - calls it with a TIMEOUT
       - on a retryable error (timeout, 429, 5xx) RETRIES with exponential backoff
       - on a non-retryable error (bad key, bad request) moves on at once
  4. FAILOVER: if one provider gives up, the next one is tried
  5. LOGS every attempt: provider, model, tokens, latency, cost, status, error

Ramen-shop picture: the gateway is the shop manager. If the main noodle supplier doesn't
answer the phone, the manager tries again a couple of times, then calls the backup supplier,
and writes every call and its cost in the notebook.
"""

import time
from dataclasses import dataclass, field

from app.llm.providers import ProviderError


class AllProvidersFailed(Exception):
    """Every provider failed (or was skipped). The API turns this into HTTP 503."""


class BudgetExceeded(Exception):
    """Today's spending limit is reached. The API turns this into HTTP 429."""


@dataclass
class CircuitBreaker:
    """
    After `threshold` failures in a row, stop calling the provider for `cooldown` seconds
    ("open" circuit). Saves time and money instead of hammering a provider that is down.
    """
    threshold: int = 3
    cooldown: float = 60.0
    failures: int = 0
    opened_at: float = 0.0

    def is_open(self, now):
        if self.failures < self.threshold:
            return False
        if now - self.opened_at >= self.cooldown:
            self.failures = 0                  # cooldown over: give the provider another chance
            return False
        return True

    def record_success(self):
        self.failures = 0

    def record_failure(self, now):
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = now


@dataclass
class GatewayResponse:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    attempts: int


@dataclass
class LLMGateway:
    providers: list                              # in priority order
    prices: dict                                 # model -> (USD per 1M input tokens, per 1M output tokens)
    log_call: callable                           # writes one attempt somewhere (DB in the app, a list in tests)
    spent_today: callable                        # returns today's cost so far in USD
    daily_budget_usd: float = 1.0
    max_retries: int = 2                         # extra tries per provider for retryable errors
    backoff_seconds: float = 0.5                 # 0.5s, 1s, 2s...
    timeout_seconds: float = 20.0
    sleep: callable = time.sleep                 # replaceable in tests (no real waiting)
    clock: callable = time.monotonic
    breakers: dict = field(default_factory=dict)

    def cost(self, model, input_tokens, output_tokens):
        price_in, price_out = self.prices.get(model, (0.0, 0.0))
        return (input_tokens * price_in + output_tokens * price_out) / 1_000_000

    def chat(self, messages, max_tokens=512):
        if self.spent_today() >= self.daily_budget_usd:
            raise BudgetExceeded(f"Daily LLM budget of ${self.daily_budget_usd:.2f} reached")

        attempts = 0
        errors = []
        for provider in self.providers:
            breaker = self.breakers.setdefault(provider.name, CircuitBreaker())
            if breaker.is_open(self.clock()):
                errors.append(f"{provider.name}: circuit open, skipped")
                continue

            for retry in range(self.max_retries + 1):
                attempts += 1
                start = self.clock()
                try:
                    result = provider.generate(messages, max_tokens=max_tokens, timeout=self.timeout_seconds)
                except ProviderError as exc:
                    latency_ms = int((self.clock() - start) * 1000)
                    breaker.record_failure(self.clock())
                    self.log_call(provider=provider.name, model=getattr(provider, "model", "?"),
                                  input_tokens=0, output_tokens=0, cost_usd=0.0,
                                  latency_ms=latency_ms, status="error", error=str(exc))
                    errors.append(f"{provider.name}: {exc}")
                    if exc.retryable and retry < self.max_retries and not breaker.is_open(self.clock()):
                        self.sleep(self.backoff_seconds * (2 ** retry))   # exponential backoff
                        continue
                    break                                                  # give up -> failover

                latency_ms = int((self.clock() - start) * 1000)
                breaker.record_success()
                cost = self.cost(result.model, result.input_tokens, result.output_tokens)
                self.log_call(provider=result.provider, model=result.model,
                              input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                              cost_usd=cost, latency_ms=latency_ms, status="ok", error=None)
                return GatewayResponse(text=result.text, provider=result.provider, model=result.model,
                                       input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                                       cost_usd=cost, latency_ms=latency_ms, attempts=attempts)

        raise AllProvidersFailed("; ".join(errors) or "no providers configured")
