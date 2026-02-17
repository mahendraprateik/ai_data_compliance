"""Ambient PII monitoring graph built with LangGraph.

Nodes:
  check_schema_changes → scan_new_elements → generate_report
                       → full_pii_scan → generate_report
  alert (for high-risk findings)

Conditional routing:
  - Schema changes detected → scan new elements
  - No changes + scheduled full scan → full PII scan
  - No changes + not scheduled → END
  - High-risk PII found in any scan → alert → generate_report
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TypedDict

from langgraph.graph import END, StateGraph

from tools.db_tools import get_all_tables, get_table_schema
from tools.pii_tools import scan_table_for_pii
from tools.schema_monitor import detect_schema_changes, snapshot_schema


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class MonitorState(TypedDict, total=False):
    """State passed through the monitoring graph."""
    schema_diff: dict
    new_tables: list[str]
    new_columns: list[dict]
    scan_results: list[dict]
    high_risk_findings: list[dict]
    report: str
    alerts: list[str]
    full_scan_requested: bool
    run_timestamp: str


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def check_schema_changes(state: MonitorState) -> MonitorState:
    """Detect schema drift since last snapshot."""
    diff = detect_schema_changes.invoke({})

    new_tables = diff.get("added_tables", [])
    new_columns = diff.get("column_changes", [])

    # Save a fresh snapshot if changes were found
    if diff.get("has_changes"):
        snapshot_schema.invoke({})

    return {
        **state,
        "schema_diff": diff,
        "new_tables": new_tables,
        "new_columns": [c for c in new_columns if c.get("change") == "added"],
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
    }


def scan_new_elements(state: MonitorState) -> MonitorState:
    """Scan only newly added tables / columns for PII."""
    results: list[dict] = []
    high_risk: list[dict] = []

    # Scan entire new tables
    for table in state.get("new_tables", []):
        report = scan_table_for_pii.invoke({"table_name": table})
        results.append(report)
        if isinstance(report, dict):
            high_risk.extend(report.get("high_risk_findings", []))

    # For new columns on existing tables, scan those columns via table scan
    scanned_tables: set[str] = set(state.get("new_tables", []))
    for col_change in state.get("new_columns", []):
        table = col_change["table"]
        if table not in scanned_tables:
            report = scan_table_for_pii.invoke({"table_name": table})
            results.append(report)
            scanned_tables.add(table)
            if isinstance(report, dict):
                high_risk.extend(report.get("high_risk_findings", []))

    return {
        **state,
        "scan_results": results,
        "high_risk_findings": high_risk,
    }


def full_pii_scan(state: MonitorState) -> MonitorState:
    """Scan every table in the database for PII."""
    tables = get_all_tables.invoke({})
    results: list[dict] = []
    high_risk: list[dict] = []

    for table in tables:
        if isinstance(table, str) and not table.startswith("Error"):
            report = scan_table_for_pii.invoke({"table_name": table})
            results.append(report)
            if isinstance(report, dict):
                high_risk.extend(report.get("high_risk_findings", []))

    return {
        **state,
        "scan_results": results,
        "high_risk_findings": high_risk,
    }


def generate_report(state: MonitorState) -> MonitorState:
    """Produce a human-readable PII report."""
    lines: list[str] = []
    ts = state.get("run_timestamp", datetime.now(timezone.utc).isoformat())
    lines.append(f"=== PII Monitoring Report — {ts} ===\n")

    # Schema changes
    diff = state.get("schema_diff", {})
    if diff.get("has_changes"):
        lines.append("## Schema Changes Detected")
        for t in diff.get("added_tables", []):
            lines.append(f"  + New table: {t}")
        for t in diff.get("dropped_tables", []):
            lines.append(f"  - Dropped table: {t}")
        for c in diff.get("column_changes", []):
            lines.append(f"  ~ {c['change']}: {c['table']}.{c['column']}")
        lines.append("")
    elif diff.get("baseline_created"):
        lines.append("## Baseline snapshot created (first run)\n")
    else:
        lines.append("## No schema changes detected\n")

    # Scan results
    scan_results = state.get("scan_results", [])
    if scan_results:
        lines.append("## PII Scan Results")
        for sr in scan_results:
            if not isinstance(sr, dict):
                continue
            table = sr.get("table", "unknown")
            lines.append(f"\n### Table: {table}")
            for cr in sr.get("column_reports", []):
                if not isinstance(cr, dict):
                    continue
                col = cr.get("column", "?")
                pii_types = cr.get("pii_types", {})
                if pii_types:
                    for pt, info in pii_types.items():
                        lines.append(
                            f"  [{pt.upper()}] {table}.{col} "
                            f"— {info['count']} match(es), "
                            f"confidence: {info['max_confidence']:.0%}"
                        )
                        if info.get("sample_matches"):
                            samples = ", ".join(info["sample_matches"][:3])
                            lines.append(f"    samples: {samples}")
        lines.append("")

    # High risk summary
    high_risk = state.get("high_risk_findings", [])
    if high_risk:
        lines.append("## HIGH-RISK FINDINGS")
        for hr in high_risk:
            lines.append(
                f"  *** {hr['pii_type'].upper()} in column '{hr['column']}' "
                f"(confidence: {hr['confidence']:.0%}) ***"
            )
        lines.append("")

    # Alerts
    alerts = state.get("alerts", [])
    if alerts:
        lines.append("## Alerts Sent")
        for a in alerts:
            lines.append(f"  - {a}")
        lines.append("")

    if not scan_results and not high_risk:
        lines.append("No PII findings to report.\n")

    report = "\n".join(lines)
    return {**state, "report": report}


def alert(state: MonitorState) -> MonitorState:
    """Flag high-risk PII findings."""
    alerts: list[str] = []
    for hr in state.get("high_risk_findings", []):
        msg = (
            f"ALERT: {hr['pii_type'].upper()} detected in column "
            f"'{hr['column']}' (confidence: {hr['confidence']:.0%})"
        )
        alerts.append(msg)
        print(f"[PII MONITOR] {msg}")
    return {**state, "alerts": alerts}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _route_after_schema_check(state: MonitorState) -> str:
    """Decide next step after checking schema changes."""
    diff = state.get("schema_diff", {})
    has_changes = diff.get("has_changes", False)
    full_requested = state.get("full_scan_requested", False)

    if has_changes:
        return "scan_new_elements"
    elif full_requested:
        return "full_pii_scan"
    else:
        return "generate_report"


def _route_after_scan(state: MonitorState) -> str:
    """Route to alert if high-risk PII was found."""
    if state.get("high_risk_findings"):
        return "alert"
    return "generate_report"


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

def build_monitor_graph():
    """Construct and compile the PII monitoring graph."""
    graph = StateGraph(MonitorState)

    graph.add_node("check_schema_changes", check_schema_changes)
    graph.add_node("scan_new_elements", scan_new_elements)
    graph.add_node("full_pii_scan", full_pii_scan)
    graph.add_node("generate_report", generate_report)
    graph.add_node("alert", alert)

    graph.set_entry_point("check_schema_changes")

    graph.add_conditional_edges(
        "check_schema_changes",
        _route_after_schema_check,
        {
            "scan_new_elements": "scan_new_elements",
            "full_pii_scan": "full_pii_scan",
            "generate_report": "generate_report",
        },
    )

    graph.add_conditional_edges(
        "scan_new_elements",
        _route_after_scan,
        {"alert": "alert", "generate_report": "generate_report"},
    )

    graph.add_conditional_edges(
        "full_pii_scan",
        _route_after_scan,
        {"alert": "alert", "generate_report": "generate_report"},
    )

    graph.add_edge("alert", "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile()


monitor_graph = build_monitor_graph()
