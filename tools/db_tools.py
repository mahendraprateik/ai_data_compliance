"""SQLite database tools for inspecting and querying the Hacker News database."""

import os
import sqlite3
from pathlib import Path

from langchain_core.tools import tool

DB_PATH = os.environ.get(
    "HACKERNEWS_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "hackernews.db"),
)


def _get_connection() -> sqlite3.Connection:
    """Return a read-only SQLite connection."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@tool
def get_all_tables() -> list[str]:
    """List all table names in the SQLite database."""
    try:
        conn = _get_connection()
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        conn.close()
        return [r["name"] for r in rows]
    except Exception as e:
        return [f"Error listing tables: {e}"]


@tool
def get_table_schema(table_name: str) -> list[dict]:
    """Get column names, types, and constraints for a given table.

    Args:
        table_name: Name of the table to inspect.
    """
    try:
        conn = _get_connection()
        # Validate table exists
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        if not exists:
            conn.close()
            return [{"error": f"Table '{table_name}' not found"}]

        rows = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
        conn.close()
        return [
            {
                "column_name": r["name"],
                "type": r["type"],
                "nullable": not r["notnull"],
                "default": r["dflt_value"],
                "primary_key": bool(r["pk"]),
            }
            for r in rows
        ]
    except Exception as e:
        return [{"error": f"Error getting schema for '{table_name}': {e}"}]


@tool
def sample_table_data(table_name: str, limit: int = 10) -> list[dict]:
    """Fetch N sample rows from a table.

    Args:
        table_name: Name of the table to sample.
        limit: Number of rows to return (default 10).
    """
    try:
        conn = _get_connection()
        exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        if not exists:
            conn.close()
            return [{"error": f"Table '{table_name}' not found"}]

        rows = conn.execute(
            f"SELECT * FROM '{table_name}' LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        return [{"error": f"Error sampling '{table_name}': {e}"}]


@tool
def run_read_only_query(query: str) -> list[dict]:
    """Execute a read-only SELECT query against the database.

    Only SELECT statements are allowed. Any other SQL statement type will be
    rejected.

    Args:
        query: A SQL SELECT query to execute.
    """
    try:
        stripped = query.strip().rstrip(";").strip()
        # Block non-SELECT statements
        first_word = stripped.split()[0].upper() if stripped else ""
        if first_word != "SELECT":
            return [{"error": "Only SELECT queries are allowed."}]

        conn = _get_connection()
        rows = conn.execute(query).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        return [{"error": f"Query error: {e}"}]


@tool
def get_database_metadata() -> list[dict]:
    """Return row counts and table info for all tables in the database.

    Useful for detecting new tables or data growth.
    """
    try:
        conn = _get_connection()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

        metadata = []
        for t in tables:
            name = t["name"]
            count = conn.execute(f"SELECT COUNT(*) as cnt FROM '{name}'").fetchone()[
                "cnt"
            ]
            col_count = len(
                conn.execute(f"PRAGMA table_info('{name}')").fetchall()
            )
            metadata.append(
                {
                    "table_name": name,
                    "row_count": count,
                    "column_count": col_count,
                }
            )

        conn.close()
        return metadata
    except Exception as e:
        return [{"error": f"Error getting metadata: {e}"}]
