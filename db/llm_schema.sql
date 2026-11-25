-- Log of every LLM call made through the gateway (one row per attempt).
-- Kept separate from schema.sql so reloading the fleet data never deletes the call history.
CREATE TABLE IF NOT EXISTS llm_calls (
    call_id        BIGSERIAL PRIMARY KEY,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    provider       TEXT NOT NULL,             -- gemini / ollama
    model          TEXT NOT NULL,
    input_tokens   INTEGER NOT NULL DEFAULT 0,
    output_tokens  INTEGER NOT NULL DEFAULT 0,
    cost_usd       NUMERIC(12, 6) NOT NULL DEFAULT 0,
    latency_ms     INTEGER NOT NULL,
    status         TEXT NOT NULL,             -- ok / error
    error          TEXT                       -- NULL when status = ok
);

CREATE INDEX IF NOT EXISTS llm_calls_created_at_idx ON llm_calls (created_at);
