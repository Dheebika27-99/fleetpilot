"""
Build the knowledge base: load documents, split into chunks, embed, store in pgvector.

Documents:
  1. docs/policies/*.md          sample maintenance policies (fictional company, committed)
  2. README.md                   what FleetPilot itself is (so the bot stops hallucinating it!)
  3. data/docs/nhtsa_recalls.json real NHTSA recall notices (run the download script first)

Re-running is safe: each document is replaced, not duplicated.

Run:  python -m rag.ingest
"""

import json
from pathlib import Path

import psycopg

from app.config import DATABASE_URL
from rag.chunking import chunk_text
from rag.embeddings import OllamaEmbedder, to_pgvector

ROOT = Path(__file__).resolve().parent.parent


def load_documents():
    """Return a list of dicts: doc_id, source, title, url, text."""
    docs = []
    for path in sorted((ROOT / "docs" / "policies").glob("*.md")):
        if path.name == "README.md":
            continue
        text = path.read_text()
        title = text.splitlines()[0].lstrip("# ").strip()
        docs.append({"doc_id": f"policy:{path.stem}", "source": "policy", "title": title,
                     "url": f"docs/policies/{path.name}", "text": text})

    readme = ROOT / "README.md"
    if readme.exists():
        docs.append({"doc_id": "readme:fleetpilot", "source": "readme", "title": "FleetPilot README",
                     "url": "README.md", "text": readme.read_text()})

    recalls_file = ROOT / "data" / "docs" / "nhtsa_recalls.json"
    if recalls_file.exists():
        for r in json.loads(recalls_file.read_text()):
            vehicles = ", ".join(r["vehicles"][:12]) + (" and more" if len(r["vehicles"]) > 12 else "")
            text = (f"NHTSA recall {r['campaign']} ({r['manufacturer']}, reported {r['report_date']})\n\n"
                    f"Vehicles: {vehicles}\n\nComponent: {r['component']}\n\n"
                    f"Summary: {r['summary']}\n\nConsequence: {r['consequence']}\n\nRemedy: {r['remedy']}")
            docs.append({"doc_id": f"nhtsa:{r['campaign']}", "source": "nhtsa",
                         "title": f"Recall {r['campaign']}: {r['component']}",
                         "url": f"https://www.nhtsa.gov/recalls?nhtsaId={r['campaign']}", "text": text})
    else:
        print("Note: no NHTSA file yet. Run: python scripts/download_nhtsa_recalls.py")
    return docs


def ingest(docs, embedder, conn):
    total_chunks = 0
    with conn.cursor() as cur:
        cur.execute((ROOT / "db" / "rag_schema.sql").read_text())
        for doc in docs:
            chunks = chunk_text(doc["text"])
            vectors = embedder.embed(chunks)
            # replace this document completely (its chunks are deleted by ON DELETE CASCADE)
            cur.execute("DELETE FROM documents WHERE doc_id = %s", [doc["doc_id"]])
            cur.execute("INSERT INTO documents (doc_id, source, title, url) VALUES (%s, %s, %s, %s)",
                        [doc["doc_id"], doc["source"], doc["title"], doc["url"]])
            for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
                cur.execute("INSERT INTO doc_chunks (doc_id, chunk_index, content, embedding) "
                            "VALUES (%s, %s, %s, %s::vector)", [doc["doc_id"], i, chunk, to_pgvector(vec)])
            total_chunks += len(chunks)
    return total_chunks


def main():
    docs = load_documents()
    by_source = {}
    for d in docs:
        by_source[d["source"]] = by_source.get(d["source"], 0) + 1
    print(f"Loaded {len(docs)} documents: {by_source}")
    with psycopg.connect(DATABASE_URL) as conn:
        n = ingest(docs, OllamaEmbedder(), conn)
    print(f"Stored {n} chunks with embeddings in doc_chunks.")


if __name__ == "__main__":
    main()
