"""
Lakebase (Databricks-managed Postgres) connection helper.

Connects using a single LAKEBASE_URL (a standard Postgres connection URL,
e.g. postgresql://role:password@host:5432/databricks_postgres?sslmode=require)
pointing at a native Postgres role with a static, non-expiring password.
This keeps setup to a single secret instead of five separate env vars.
"""

import base64
import os
from contextlib import contextmanager
from urllib.parse import urlparse

import psycopg2
from databricks.sdk import WorkspaceClient
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine

_w = WorkspaceClient()

_SCOPE = os.environ.get("LAKEBASE_SECRET_SCOPE", "database")
_KEY = os.environ.get("LAKEBASE_SECRET_KEY", "lakebase-url")


def _lakebase_url() -> str:
    """Fetch and decode the Lakebase connection URL from the Databricks secret scope."""
    import sys
    print(f"DEBUG: Fetching secret from scope='{_SCOPE}', key='{_KEY}'", file=sys.stderr)
    secret = _w.secrets.get_secret(scope=_SCOPE, key=_KEY)
    decoded_url = base64.b64decode(secret.value).decode("utf-8")
    
    # Log URL format (mask password for security)
    if "@" in decoded_url and ":" in decoded_url:
        parts = decoded_url.split("@")
        masked_url = parts[0].rsplit(":", 1)[0] + ":***PASSWORD***@" + parts[1]
    else:
        masked_url = decoded_url[:50] + "..."
    print(f"DEBUG: Retrieved URL format: {masked_url}", file=sys.stderr)
    print(f"DEBUG: URL contains password: {'yes' if '@' in decoded_url and decoded_url.split('@')[0].count(':') > 1 else 'no'}", file=sys.stderr)
    
    return decoded_url


@contextmanager
def get_connection(database: str | None = None):
    """Yield a raw psycopg2 connection with a RealDictCursor factory.
    
    Parses the connection URL and passes parameters individually to psycopg2,
    following the same pattern as the working notebook.
    
    Args:
        database: Optional database name to connect to. If provided, overrides
                  the database in the connection URL.
    """
    url = _lakebase_url()
    parsed = urlparse(url)
    
    # Use the provided database name, or fall back to the one in the URL
    dbname = database or parsed.path.lstrip('/')
    
    # Extract connection details from URL
    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        dbname=dbname,
        user=parsed.username,
        password=parsed.password,
        sslmode='require',
        cursor_factory=RealDictCursor
    )
    try:
        yield conn
    finally:
        conn.close()


def get_engine():
    """Return a SQLAlchemy engine for Lakebase."""
    return create_engine(_lakebase_url())


def run_query(sql: str, params: tuple | dict | None = None, database: str | None = None) -> list[dict]:
    """Run a read query against Lakebase and return rows as list[dict].
    
    Args:
        sql: SQL query to execute
        params: Optional query parameters
        database: Optional database name to connect to (overrides URL default)
    """
    with get_connection(database=database) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def run_write(sql: str, params: tuple | dict | None = None, database: str | None = None) -> int:
    """Run an INSERT/UPDATE/DELETE against Lakebase, return affected row count.
    
    Args:
        sql: SQL query to execute
        params: Optional query parameters
        database: Optional database name to connect to (overrides URL default)
    """
    with get_connection(database=database) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            conn.commit()
            return cur.rowcount
