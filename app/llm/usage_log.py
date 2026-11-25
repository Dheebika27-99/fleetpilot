"""
Writes each LLM call to the llm_calls table, and reads today's spending.

If the database is down, logging must NOT break the chat: we print a warning and carry on.
(The answer matters more to the user than our bookkeeping.)
"""

import psycopg

from app.config import DATABASE_URL


def log_call(provider, model, input_tokens, output_tokens, cost_usd, latency_ms, status, error):
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=3) as conn:
            conn.execute(
                """INSERT INTO llm_calls (provider, model, input_tokens, output_tokens,
                                          cost_usd, latency_ms, status, error)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                [provider, model, input_tokens, output_tokens, cost_usd, latency_ms, status, error],
            )
    except psycopg.Error as exc:
        print(f"WARNING: could not log LLM call: {type(exc).__name__}")


def spent_today():
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=3) as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_calls WHERE created_at >= date_trunc('day', now())"
            ).fetchone()
            return float(row[0])
    except psycopg.Error:
        return 0.0


def usage_summary(hours=24):
    """Per provider: calls, errors, average latency, tokens and cost in the last N hours."""
    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            """SELECT provider,
                      COUNT(*)                                  AS calls,
                      COUNT(*) FILTER (WHERE status = 'error')  AS errors,
                      ROUND(AVG(latency_ms) FILTER (WHERE status = 'ok')) AS avg_latency_ms,
                      SUM(input_tokens)                         AS input_tokens,
                      SUM(output_tokens)                        AS output_tokens,
                      SUM(cost_usd)                             AS cost_usd
               FROM llm_calls
               WHERE created_at >= now() - make_interval(hours => %s)
               GROUP BY provider
               ORDER BY provider""",
            [hours],
        ).fetchall()
    keys = ["provider", "calls", "errors", "avg_latency_ms", "input_tokens", "output_tokens", "cost_usd"]
    out = []
    for r in rows:
        d = dict(zip(keys, r))
        d["avg_latency_ms"] = int(d["avg_latency_ms"]) if d["avg_latency_ms"] is not None else None
        d["cost_usd"] = float(d["cost_usd"])
        out.append(d)
    return out
