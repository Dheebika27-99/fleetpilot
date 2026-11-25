"""
RAG answer tests: fake embedder (no Ollama) + fake LLM provider (no key).
The knowledge base is built inside a transaction that is rolled back afterwards.
"""

from fastapi.testclient import TestClient

from app.db import get_conn
from app.llm.gateway import LLMGateway
from app.llm.providers import LLMResult
from app.llm.router import get_gateway
from app.main import app
from app.rag_router import get_embedder
from rag.answer import NOT_FOUND, answer_question, build_prompt, extract_citations
from rag.ingest import ingest
from tests.test_rag import DOCS, FakeEmbedder, conn  # noqa: F401  (conn = rollback fixture)


class ScriptedLLM:
    """Fake provider that returns a fixed text and remembers the prompt it was given."""
    name = "fake"
    model = "fake-model"

    def __init__(self, text):
        self.text = text
        self.last_messages = None
        self.calls = 0

    def generate(self, messages, max_tokens=512, timeout=20.0):
        self.calls += 1
        self.last_messages = messages
        return LLMResult(text=self.text, provider=self.name, model=self.model,
                         input_tokens=200, output_tokens=30)


def gateway_with(llm):
    return LLMGateway(providers=[llm], prices={}, log_call=lambda **row: None,
                      spent_today=lambda: 0.0, sleep=lambda s: None)


def test_citations_ignore_invented_numbers():
    assert extract_citations("Check pads [1] and discs [2][9].", n_sources=3) == [1, 2]


def test_prompt_contains_numbered_sources_and_rules():
    hits = [{"title": "Brakes", "source": "policy", "content": "Inspect every 20,000 km."}]
    messages = build_prompt("How often?", hits)
    assert "Cite the sources" in messages[0]["content"]
    assert "[1] Brakes (policy)" in messages[1]["content"]
    assert "Question: How often?" in messages[1]["content"]


def test_answer_uses_sources_and_reports_citations(conn):  # noqa: F811
    ingest(DOCS, FakeEmbedder(), conn)
    llm = ScriptedLLM("Inspect brake pads every 20,000 km [1].")
    r = answer_question("when should brake pads be inspected", FakeEmbedder(), conn,
                        gateway_with(llm), top_k=2, min_similarity=0.1)
    assert r.answered_from_sources and r.cited == [1]
    assert r.sources[0]["doc_id"] == "test:brakes"
    assert "brake pads" in llm.last_messages[1]["content"]   # the LLM really saw the source


def test_weak_match_says_i_dont_know_without_calling_the_llm(conn):  # noqa: F811
    ingest(DOCS, FakeEmbedder(), conn)
    llm = ScriptedLLM("should never be used")
    r = answer_question("best ramen shop in shibuya", FakeEmbedder(), conn,
                        gateway_with(llm), min_similarity=0.5)
    assert r.answer == NOT_FOUND and not r.answered_from_sources
    assert llm.calls == 0                                       # no LLM call, no cost


def test_ask_endpoint(conn):  # noqa: F811
    ingest(DOCS, FakeEmbedder(), conn)
    llm = ScriptedLLM("Charge electric vehicles overnight to 80 percent [1].")
    app.dependency_overrides[get_conn] = lambda: conn
    app.dependency_overrides[get_embedder] = lambda: FakeEmbedder()
    app.dependency_overrides[get_gateway] = lambda: gateway_with(llm)
    try:
        r = TestClient(app).post("/ask", json={"question": "battery low warning on electric vehicles"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    body = r.json()
    assert body["cited"] == [1] and body["sources"][0]["doc_id"] == "test:battery"
    assert body["provider"] == "fake"
