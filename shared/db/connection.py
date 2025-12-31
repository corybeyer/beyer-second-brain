"""Database connection utilities for Second Brain."""

import os
from contextlib import contextmanager
from typing import Generator

import psycopg2
from psycopg2.extensions import connection as PgConnection
from dotenv import load_dotenv

load_dotenv()


def get_connection_params() -> dict:
    """Get PostgreSQL connection parameters from environment."""
    return {
        "host": os.environ["POSTGRES_HOST"],
        "port": int(os.environ.get("POSTGRES_PORT", 5432)),
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
        "sslmode": "require",
    }


def get_connection() -> PgConnection:
    """Create a new database connection."""
    return psycopg2.connect(**get_connection_params())


@contextmanager
def get_db_connection() -> Generator[PgConnection, None, None]:
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_db_cursor(commit: bool = True):
    """Context manager for database cursor with automatic commit."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            yield cursor
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
