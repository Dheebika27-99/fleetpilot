"""
RAG answers: the "open-book exam".

  1. SEARCH   find the most relevant chunks for the question            (rag/search.py)
  2. CHECK    if even the best chunk is a weak match, say "I don't know"
              WITHOUT calling the LLM (no guessing, no cost)
  3. PROMPT   give the LLM the question + the numbered sources [1], [2]...
              with strict rules: use only these sources, cite them, admit when unsure
  4. ANSWER   via the LLM gateway (retries, failover, cost logging all included)
  5. CITATIONS keep only the source numbers the answer really used; drop invented ones

Ramen picture: the chef may only cook with the ingredients on the counter,
and must say which ingredient each part of the dish came from.
"""

import re
import time
from dataclasses import dataclass, field

from rag.search import search

NOT_FOUND = "I don't know. The FleetPilot documents don't cover this question."

SYSTEM_PROMPT = """You are FleetPilot's assistant for fleet managers.
Answer ONLY using the numbered sources provided. Rules:
- Cite the sources you use with their numbers in square brackets, like [1] or [2][3].
- If the sources do not contain the answer, reply exactly: "%s"
- Do not use outside knowledge and do not guess.
- Be short and practical: 2 to 5 sentences, or a short list.
- Company policies are internal sample policies; recalls are official NHTSA notices.""" % NOT_FOUND


@dataclass
class RagAnswer:
    answer: str
    sources: list                         # every source shown to the LLM
    cited: list = field(default_factory=list)   # source numbers the answer actually used
    provider: str = None
    model: str = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    retrieval_ms: int = 0
    llm_ms: int = 0
    answered_from_sources: bool = False


def build_prompt(question, hits):
    blocks = []
    for i, h in enumerate(hits, 1):
        blocks.append(f"[{i}] {h['title']} ({h['source']})\n{h['content']}")
    sources_text = "\n\n".join(blocks)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Sources:\n\n{sources_text}\n\nQuestion: {question}"},
    ]


def extract_citations(text, n_sources):
    """Numbers like [2] that point to a real source. Invented numbers like [9] are dropped."""
    found = {int(n) for n in re.findall(r"\[(\d+)\]", text)}
    return sorted(n for n in found if 1 <= n <= n_sources)


def answer_question(question, embedder, conn, gateway, top_k=5, min_similarity=0.5, max_tokens=400):
    t0 = time.monotonic()
    hits = search(question, embedder, conn, top_k=top_k)
    retrieval_ms = int((time.monotonic() - t0) * 1000)

    sources = [{"n": i, "doc_id": h["doc_id"], "title": h["title"], "source": h["source"],
                "url": h["url"], "similarity": round(float(h["similarity"]), 3)}
               for i, h in enumerate(hits, 1)]

    if not hits or hits[0]["similarity"] < min_similarity:
        return RagAnswer(answer=NOT_FOUND, sources=sources, retrieval_ms=retrieval_ms)

    t1 = time.monotonic()
    r = gateway.chat(build_prompt(question, hits), max_tokens=max_tokens)
    llm_ms = int((time.monotonic() - t1) * 1000)

    cited = extract_citations(r.text, len(hits))
    return RagAnswer(answer=r.text.strip(), sources=sources, cited=cited, provider=r.provider,
                     model=r.model, input_tokens=r.input_tokens, output_tokens=r.output_tokens,
                     cost_usd=r.cost_usd, retrieval_ms=retrieval_ms, llm_ms=llm_ms,
                     answered_from_sources=bool(cited) and NOT_FOUND not in r.text)
