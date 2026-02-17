"""Ambient PII monitor — runs the monitoring graph on a configurable interval.

Usage:
    python monitor.py                    # run once
    python monitor.py --loop             # run every 5 minutes
    python monitor.py --loop --interval 60  # run every 60 seconds
    python monitor.py --full-scan        # force a full PII scan of all tables

Results are stored in a `pii_audit_log` table in the SQLite database.
"""

import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on the path so tool imports work
sys.path.insert(0, str(Path(__file__).resolve().parent))

from graphs.pii_monitor import monitor_graph

DB_PATH = os.environ.get(
    "HACKERNEWS_DB_PATH",
    str(Path(__file__).resolve().parent / "hackernews.db"),
)

AUDIT_LOG_DB = os.environ.get(
    "AUDIT_LOG_DB_PATH",
    DB_PATH,
)


def _ensure_audit_table() -> None:
    """Create the pii_audit_log table if it doesn't exist."""
    conn = sqlite3.connect(AUDIT_LOG_DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pii_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_timestamp TEXT NOT NULL,
            has_schema_changes INTEGER NOT NULL DEFAULT 0,
            has_high_risk INTEGER NOT NULL DEFAULT 0,
            tables_scanned INTEGER NOT NULL DEFAULT 0,
            high_risk_count INTEGER NOT NULL DEFAULT 0,
            report TEXT NOT NULL,
            alerts TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def _save_audit(state: dict) -> None:
    """Persist a monitoring run's results to the audit log table."""
    conn = sqlite3.connect(AUDIT_LOG_DB)
    diff = state.get("schema_diff", {})
    high_risk = state.get("high_risk_findings", [])
    scan_results = state.get("scan_results", [])
    alerts = state.get("alerts", [])

    conn.execute(
        """
        INSERT INTO pii_audit_log
            (run_timestamp, has_schema_changes, has_high_risk,
             tables_scanned, high_risk_count, report, alerts)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            state.get("run_timestamp", datetime.now(timezone.utc).isoformat()),
            int(diff.get("has_changes", False)),
            int(bool(high_risk)),
            len(scan_results),
            len(high_risk),
            state.get("report", ""),
            "\n".join(alerts) if alerts else None,
        ),
    )
    conn.commit()
    conn.close()


def run_once(full_scan: bool = False) -> dict:
    """Execute a single monitoring run."""
    print(f"\n{'='*60}")
    print(f"PII Monitor run — {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}")

    initial_state = {"full_scan_requested": full_scan}
    result = monitor_graph.invoke(initial_state)

    # Print report
    print(result.get("report", "(no report generated)"))

    # Save to audit log
    _ensure_audit_table()
    _save_audit(result)

    high_risk = result.get("high_risk_findings", [])
    if high_risk:
        print(f"\n*** {len(high_risk)} HIGH-RISK finding(s) logged ***")

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Ambient PII Monitor")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously on an interval",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Seconds between runs when --loop is set (default: 300 = 5 min)",
    )
    parser.add_argument(
        "--full-scan",
        action="store_true",
        help="Force a full PII scan of all tables",
    )
    args = parser.parse_args()

    if args.loop:
        print(f"Starting ambient PII monitor (interval: {args.interval}s)")
        print("Press Ctrl+C to stop.\n")
        try:
            while True:
                run_once(full_scan=args.full_scan)
                print(f"\nNext run in {args.interval} seconds...")
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nMonitor stopped.")
    else:
        run_once(full_scan=args.full_scan)


if __name__ == "__main__":
    main()
