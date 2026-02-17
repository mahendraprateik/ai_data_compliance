"""Schema change detection tools for ambient database monitoring."""

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.tools import tool

DB_PATH = os.environ.get(
    "HACKERNEWS_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "hackernews.db"),
)

SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "schema_snapshots"


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _current_schema() -> dict:
    """Capture the current database schema as a dict."""
    conn = _get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()

    schema: dict = {}
    for t in tables:
        name = t["name"]
        cols = conn.execute(f"PRAGMA table_info('{name}')").fetchall()
        schema[name] = [
            {
                "column_name": c["name"],
                "type": c["type"],
                "nullable": not c["notnull"],
                "primary_key": bool(c["pk"]),
            }
            for c in cols
        ]
    conn.close()
    return schema


def _latest_snapshot_path() -> Path | None:
    """Return the path to the most recent snapshot file, or None."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(SNAPSHOT_DIR.glob("snapshot_*.json"))
    return files[-1] if files else None


def _diff_schemas(old: dict, new: dict) -> dict:
    """Compare two schema dicts and return a structured diff."""
    old_tables = set(old.keys())
    new_tables = set(new.keys())

    added_tables = sorted(new_tables - old_tables)
    dropped_tables = sorted(old_tables - new_tables)

    column_changes: list[dict] = []

    for table in sorted(old_tables & new_tables):
        old_cols = {c["column_name"]: c for c in old[table]}
        new_cols = {c["column_name"]: c for c in new[table]}

        for col_name in sorted(set(new_cols) - set(old_cols)):
            column_changes.append(
                {
                    "table": table,
                    "column": col_name,
                    "change": "added",
                    "details": new_cols[col_name],
                }
            )
        for col_name in sorted(set(old_cols) - set(new_cols)):
            column_changes.append(
                {
                    "table": table,
                    "column": col_name,
                    "change": "dropped",
                    "details": old_cols[col_name],
                }
            )
        for col_name in sorted(set(old_cols) & set(new_cols)):
            if old_cols[col_name]["type"] != new_cols[col_name]["type"]:
                column_changes.append(
                    {
                        "table": table,
                        "column": col_name,
                        "change": "type_changed",
                        "old_type": old_cols[col_name]["type"],
                        "new_type": new_cols[col_name]["type"],
                    }
                )

    has_changes = bool(added_tables or dropped_tables or column_changes)
    return {
        "has_changes": has_changes,
        "added_tables": added_tables,
        "dropped_tables": dropped_tables,
        "column_changes": column_changes,
    }


@tool
def snapshot_schema() -> dict:
    """Take a snapshot of the current database schema and save it to disk.

    Saves a JSON file in schema_snapshots/ with a timestamp.
    Returns the snapshot metadata.
    """
    try:
        schema = _current_schema()
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"snapshot_{ts}.json"
        path = SNAPSHOT_DIR / filename

        snapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tables": schema,
        }
        path.write_text(json.dumps(snapshot, indent=2))

        return {
            "saved_to": str(path),
            "timestamp": snapshot["timestamp"],
            "table_count": len(schema),
            "tables": list(schema.keys()),
        }
    except Exception as e:
        return {"error": f"Error taking snapshot: {e}"}


@tool
def compare_schema_snapshots(old_path: str, new_path: str) -> dict:
    """Compare two schema snapshot files and return a structured diff.

    Args:
        old_path: Path to the older snapshot JSON file.
        new_path: Path to the newer snapshot JSON file.
    """
    try:
        old_data = json.loads(Path(old_path).read_text())
        new_data = json.loads(Path(new_path).read_text())

        diff = _diff_schemas(old_data["tables"], new_data["tables"])
        diff["old_timestamp"] = old_data["timestamp"]
        diff["new_timestamp"] = new_data["timestamp"]
        return diff
    except FileNotFoundError as e:
        return {"error": f"Snapshot file not found: {e}"}
    except Exception as e:
        return {"error": f"Error comparing snapshots: {e}"}


@tool
def detect_schema_changes() -> dict:
    """Compare current schema against the latest saved snapshot.

    If no snapshot exists, creates a baseline snapshot and notes that.
    Returns changes detected since the last snapshot.
    """
    try:
        current = _current_schema()
        latest_path = _latest_snapshot_path()

        if latest_path is None:
            # No baseline — create one
            result = snapshot_schema.invoke({})
            return {
                "baseline_created": True,
                "message": "No previous snapshot found. Created baseline.",
                "snapshot": result,
                "has_changes": False,
                "added_tables": [],
                "dropped_tables": [],
                "column_changes": [],
            }

        old_data = json.loads(latest_path.read_text())
        diff = _diff_schemas(old_data["tables"], current)
        diff["compared_to"] = str(latest_path)
        diff["snapshot_timestamp"] = old_data["timestamp"]
        return diff
    except Exception as e:
        return {"error": f"Error detecting schema changes: {e}"}
