"""Database connection for the API."""

import psycopg
from psycopg.rows import dict_row

from app.config import DATABASE_URL


def get_conn():
    """
    FastAPI dependency: opens a connection for one request, closes it afterwards.
    Rows come back as dictionaries, e.g. {"vehicle_id": 1, "model": "Hiace"}.

    (Simple on purpose. A connection *pool* is the next step when traffic grows.)
    """
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()
