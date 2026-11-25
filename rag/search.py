"""
Search the knowledge base: find the chunks whose meaning is closest to a question.

How: embed the question -> ask pgvector for the chunks with the smallest cosine distance.
similarity = 1 - distance  (1.0 = same meaning, around 0 = unrelated)

Run:  python -m rag.search "how often should brake pads be checked?"
"""

import sys

import psycopg
from psycopg.rows import dict_row

from app.config import DATABASE_URL
from rag.embeddings import OllamaEmbedder, to_pgvector


def search(question, embedder, conn, top_k=4):
    qvec = to_pgvector(embedder.embed([question])[0])
    return conn.execute(
        """SELECT c.doc_id, d.title, d.source, d.url, c.chunk_index, c.content,
                  1 - (c.embedding <=> %s::vector) AS similarity
           FROM doc_chunks c JOIN documents d ON d.doc_id = c.doc_id
           ORDER BY c.embedding <=> %s::vector
           LIMIT %s""",
        [qvec, qvec, top_k],
    ).fetchall()


def main():
    question = " ".join(sys.argv[1:]) or "How often should brake pads be checked?"
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        hits = search(question, OllamaEmbedder(), conn)
    print(f"\nQuestion: {question}\n")
    for i, h in enumerate(hits, 1):
        preview = " ".join(h["content"].split())[:160]
        print(f"{i}. [{h['similarity']:.2f}] {h['title']}  ({h['doc_id']})\n   {preview}...\n")


if __name__ == "__main__":
    main()
