"""
API endpoints for the LLM gateway.

  POST /llm/chat   send a message, get an answer (with provider, tokens, cost, latency)
  GET  /llm/usage  calls, errors, latency, tokens and cost per provider (last 24 h)
"""

from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import config
from app.llm.gateway import AllProvidersFailed, BudgetExceeded, LLMGateway
from app.llm.providers import GeminiProvider, OllamaProvider
from app.llm.usage_log import log_call, spent_today, usage_summary

router = APIRouter(prefix="/llm", tags=["LLM gateway"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    system: Optional[str] = Field(default=None, max_length=4000)
    max_tokens: int = Field(default=512, ge=1, le=2048)


class ChatResponse(BaseModel):
    answer: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    attempts: int


def build_providers():
    available = {}
    if config.GEMINI_API_KEY:
        available["gemini"] = GeminiProvider(config.GEMINI_API_KEY, config.GEMINI_MODEL)
    available["ollama"] = OllamaProvider(config.OLLAMA_MODEL, config.OLLAMA_URL)
    return [available[name] for name in config.LLM_PROVIDER_ORDER if name in available]


@lru_cache(maxsize=1)
def get_gateway():
    """One gateway for the whole app, so circuit breakers remember failures between requests."""
    return LLMGateway(
        providers=build_providers(),
        prices=config.LLM_PRICES,
        log_call=log_call,
        spent_today=spent_today,
        daily_budget_usd=config.LLM_DAILY_BUDGET_USD,
        max_retries=config.LLM_MAX_RETRIES,
        timeout_seconds=config.LLM_TIMEOUT_SECONDS,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, gateway: LLMGateway = Depends(get_gateway)):
    messages = []
    if request.system:
        messages.append({"role": "system", "content": request.system})
    messages.append({"role": "user", "content": request.message})
    try:
        r = gateway.chat(messages, max_tokens=request.max_tokens)
    except BudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except AllProvidersFailed as exc:
        raise HTTPException(status_code=503, detail=f"All LLM providers failed: {exc}")
    return ChatResponse(answer=r.text, provider=r.provider, model=r.model, input_tokens=r.input_tokens,
                        output_tokens=r.output_tokens, cost_usd=round(r.cost_usd, 6),
                        latency_ms=r.latency_ms, attempts=r.attempts)


@router.get("/usage")
def usage():
    return {
        "providers": usage_summary(hours=24),
        "spent_today_usd": round(spent_today(), 6),
        "daily_budget_usd": config.LLM_DAILY_BUDGET_USD,
        "provider_order": config.LLM_PROVIDER_ORDER,
    }
