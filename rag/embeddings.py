"""
Embeddings: turn text into a list of numbers (a vector) that captures its MEANING.

Texts with similar meaning get vectors that point in a similar direction, even with
different words: "brake pads worn" is close to "BRAKE_WEAR warning", far from "battery charging".

We use a small embedding model running locally in Ollama (nomic-embed-text, 768 numbers):
free, no API key, no rate limits, and our documents never leave the computer.

Ramen picture: every page gets a "flavour code". To find pages about a question,
we compare flavour codes instead of reading every page.
"""

import httpx

from app.config import EMBED_MODEL, OLLAMA_URL

EMBED_DIM = 768


class OllamaEmbedder:
    def __init__(self, model=EMBED_MODEL, base_url=OLLAMA_URL):
        self.model = model
        self.base_url = base_url

    def embed(self, texts, batch_size=32):
        vectors = []
        for i in range(0, len(texts), batch_size):
            r = httpx.post(f"{self.base_url}/api/embed",
                           json={"model": self.model, "input": texts[i:i + batch_size]}, timeout=120)
            r.raise_for_status()
            vectors.extend(r.json()["embeddings"])
        return vectors


def to_pgvector(vector):
    """Postgres pgvector text format: '[0.1,0.2,...]'"""
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"
