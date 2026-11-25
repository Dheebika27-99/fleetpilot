"""
RAG knowledge-base tests. No Ollama needed: a FAKE embedder turns words into a vector
(texts sharing words get similar vectors), which is enough to test chunking, storage and search.
Everything runs inside a transaction that is rolled back, so the real knowledge base is untouched.
"""

import hashlib
import math

import psycopg
import pytest
from psycopg.rows import dict_row

from app.config import DATABASE_URL
from rag.chunking import chunk_text
from rag.embeddings import EMBED_DIM
from rag.ingest import ingest
from rag.search import search


class FakeEmbedder:
    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.0] * EMBED_DIM
            for word in t.lower().split():
                word = word.strip(".,:;!?()*#|`'\"")
                if word:
                    v[int(hashlib.md5(word.encode()).hexdigest(), 16) % EMBED_DIM] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out


DOCS = [
    {"doc_id": "test:brakes", "source": "policy", "title": "Brakes", "url": None,
     "text": "Inspect brake pads and discs every 20,000 km. Replace pads at 3 mm."},
    {"doc_id": "test:battery", "source": "policy", "title": "Battery", "url": None,
     "text": "Charge electric vehicles overnight to 80 percent. Battery low warning means charge."},
    {"doc_id": "test:tires", "source": "policy", "title": "Tires", "url": None,
     "text": "Check tire pressure weekly with a gauge when tires are cold."},
]


@pytest.fixture
def conn():
    c = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        c.execute("CREATE EXTENSION IF NOT EXISTS vector")
    except psycopg.Error:
        c.close()
        pytest.skip("pgvector extension not available in this Postgres")
    c.execute("DROP TABLE IF EXISTS doc_chunks, documents")   # rolled back after the test
    yield c
    c.rollback()
    c.close()


def test_chunks_are_small_and_cover_the_text():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 40 for i in range(10))
    chunks = chunk_text(text, max_chars=300, overlap_chars=50)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)
    assert "Paragraph 0." in chunks[0] and "Paragraph 9." in chunks[-1]


def test_short_text_is_one_chunk():
    assert chunk_text("Just one short paragraph.") == ["Just one short paragraph."]


def test_search_finds_the_right_document(conn):
    ingest(DOCS, FakeEmbedder(), conn)
    hits = search("when should brake pads be replaced", FakeEmbedder(), conn, top_k=1)
    assert hits[0]["doc_id"] == "test:brakes"
    hits = search("battery low warning on electric vehicles", FakeEmbedder(), conn, top_k=1)
    assert hits[0]["doc_id"] == "test:battery"


def test_reingesting_does_not_duplicate(conn):
    ingest(DOCS, FakeEmbedder(), conn)
    ingest(DOCS, FakeEmbedder(), conn)
    n = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
    assert n == len(DOCS)
