"""Database connection utilities for Azure SQL."""

import os
import struct
from contextlib import contextmanager
from typing import Generator

import pyodbc
from dotenv import load_dotenv

load_dotenv()


def _get_managed_identity_token() -> bytes:
    """Get Azure AD token for managed identity authentication.

    Used when running in Azure (Function App, Container Apps).
    Returns token in the format required by pyodbc.
    """
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential()
    token = credential.get_token("https://database.windows.net/.default")

    # Convert token to bytes format required by pyodbc
    token_bytes = token.token.encode("utf-16-le")
    token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
    return token_struct


def get_connection_string() -> str:
    """Build Azure SQL connection string from environment variables."""
    server = os.environ.get("AZURE_SQL_SERVER", "")
    database = os.environ.get("AZURE_SQL_DATABASE", "secondbrain")

    # Base connection string
    conn_str = (
        f"Driver={{ODBC Driver 18 for SQL Server}};"
        f"Server=tcp:{server},1433;"
        f"Database={database};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
    )

    return conn_str


def get_connection() -> pyodbc.Connection:
    """Create a new database connection.

    Uses managed identity when running in Azure (AZURE_SQL_USE_MI=true),
    otherwise falls back to SQL authentication for local development.
    """
    conn_str = get_connection_string()
    use_managed_identity = os.environ.get("AZURE_SQL_USE_MI", "false").lower() == "true"

    if use_managed_identity:
        # Azure managed identity authentication
        token = _get_managed_identity_token()
        conn = pyodbc.connect(conn_str, attrs_before={1256: token})
    else:
        # SQL authentication for local development
        username = os.environ.get("AZURE_SQL_USERNAME", "")
        password = os.environ.get("AZURE_SQL_PASSWORD", "")
        conn_str += f"Uid={username};Pwd={password};"
        conn = pyodbc.connect(conn_str)

    return conn


@contextmanager
def get_db_connection() -> Generator[pyodbc.Connection, None, None]:
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
