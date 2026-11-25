-- Knowledge base for RAG: documents, split into chunks, each with an embedding vector.
-- Needs the pgvector extension (included in Postgres.app; CI uses the pgvector Docker image).
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    doc_id      TEXT PRIMARY KEY,          -- e.g. "policy:brakes" or "nhtsa:24V123000"
    source      TEXT NOT NULL,             -- policy / nhtsa / readme
    title       TEXT NOT NULL,
    url         TEXT,                      -- where a human can read the original
    loaded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 768 = size of the vectors made by the embedding model (nomic-embed-text)
CREATE TABLE IF NOT EXISTS doc_chunks (
    chunk_id     BIGSERIAL PRIMARY KEY,
    doc_id       TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    chunk_index  INTEGER NOT NULL,         -- 0, 1, 2... position inside the document
    content      TEXT NOT NULL,
    embedding    vector(768) NOT NULL,
    UNIQUE (doc_id, chunk_index)
);

-- HNSW index = fast "find the most similar vectors" search (cosine distance)
CREATE INDEX IF NOT EXISTS doc_chunks_embedding_idx
    ON doc_chunks USING hnsw (embedding vector_cosine_ops);
