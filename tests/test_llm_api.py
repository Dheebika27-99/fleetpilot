"""
Tests for POST /llm/chat. The real gateway is swapped for one with fake providers
(FastAPI "dependency override"), so no key or internet is needed.
"""

from fastapi.testclient import TestClient

from app.llm.gateway import LLMGateway
from app.llm.router import get_gateway
from app.main import app
from tests.test_llm_gateway import FakeProvider


def client_with(providers, spent=0.0):
    gateway = LLMGateway(providers=providers, prices={}, log_call=lambda **row: None,
                         spent_today=lambda: spent, daily_budget_usd=1.0, sleep=lambda s: None)
    app.dependency_overrides[get_gateway] = lambda: gateway
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_chat_returns_answer_and_metadata():
    client = client_with([FakeProvider("gemini", ["ok"])])
    r = client.post("/llm/chat", json={"message": "Hello"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "hello from gemini"
    assert body["provider"] == "gemini"
    assert body["input_tokens"] == 100 and body["output_tokens"] == 50


def test_chat_fails_over_to_backup():
    client = client_with([FakeProvider("gemini", ["bad_key"]), FakeProvider("ollama", ["ok"])])
    r = client.post("/llm/chat", json={"message": "Hello"})
    assert r.status_code == 200 and r.json()["provider"] == "ollama"


def test_chat_503_when_every_provider_fails():
    client = client_with([FakeProvider("gemini", ["bad_key"]), FakeProvider("ollama", ["bad_key"])])
    r = client.post("/llm/chat", json={"message": "Hello"})
    assert r.status_code == 503


def test_chat_429_when_budget_is_used_up():
    client = client_with([FakeProvider("gemini", ["ok"])], spent=5.0)
    r = client.post("/llm/chat", json={"message": "Hello"})
    assert r.status_code == 429


def test_empty_message_is_rejected():
    client = client_with([FakeProvider("gemini", ["ok"])])
    r = client.post("/llm/chat", json={"message": ""})
    assert r.status_code == 422
