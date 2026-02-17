"""PII detection tools for scanning database columns and tables."""

import re
import sqlite3
import os
from pathlib import Path

from langchain_core.tools import tool

DB_PATH = os.environ.get(
    "HACKERNEWS_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "hackernews.db"),
)

# ---------------------------------------------------------------------------
# PII regex patterns
# ---------------------------------------------------------------------------

PII_PATTERNS: dict[str, re.Pattern] = {
    "email": re.compile(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}", re.IGNORECASE
    ),
    "phone_us": re.compile(
        r"""(?x)
        (?:\+?1[\s.-]?)?          # optional country code
        (?:\(?\d{3}\)?[\s.-]?)    # area code
        \d{3}[\s.-]?\d{4}        # subscriber number
        """
    ),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(
        r"\b(?:4\d{3}|5[1-5]\d{2}|3[47]\d{2}|6(?:011|5\d{2}))"
        r"[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{1,4}\b"
    ),
    "ipv4": re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
        r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    ),
    "ipv6": re.compile(
        r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b"
    ),
    "date_of_birth": re.compile(
        r"""(?x)
        \b
        (?:
            \d{4}[-/]\d{2}[-/]\d{2}  |  # YYYY-MM-DD or YYYY/MM/DD
            \d{2}[-/]\d{2}[-/]\d{4}  |  # MM-DD-YYYY or MM/DD/YYYY
            \d{2}[-/]\d{2}[-/]\d{2}     # MM-DD-YY or MM/DD/YY
        )
        \b
        """
    ),
}

# Common private IP prefixes to filter out from IPv4 matches
_PRIVATE_IP_PREFIXES = ("10.", "172.", "192.168.", "127.", "0.")

SAMPLE_SIZE = 200  # rows to sample per column scan


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _luhn_check(number: str) -> bool:
    """Validate a credit card number using the Luhn algorithm."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
    checksum = 0
    reverse = digits[::-1]
    for i, d in enumerate(reverse):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _classify_values(values: list[str]) -> list[dict]:
    """Run PII patterns against a list of string values.

    Returns a list of findings with pii_type, matched_value, and confidence.
    """
    findings: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for val in values:
        if not val:
            continue
        text = str(val)
        for pii_type, pattern in PII_PATTERNS.items():
            for match in pattern.finditer(text):
                matched = match.group()
                key = (pii_type, matched)
                if key in seen:
                    continue
                seen.add(key)

                confidence = 0.7  # default

                if pii_type == "credit_card":
                    if _luhn_check(matched):
                        confidence = 0.95
                    else:
                        continue  # skip non-Luhn matches
                elif pii_type == "ssn":
                    confidence = 0.9
                elif pii_type == "email":
                    confidence = 0.95
                elif pii_type == "ipv4":
                    if any(matched.startswith(p) for p in _PRIVATE_IP_PREFIXES):
                        confidence = 0.3
                    else:
                        confidence = 0.6
                elif pii_type == "phone_us":
                    # Phone regex can be noisy — lower confidence
                    confidence = 0.5
                elif pii_type == "date_of_birth":
                    confidence = 0.4  # dates are common; DOB needs context

                findings.append(
                    {
                        "pii_type": pii_type,
                        "matched_value": matched,
                        "confidence": confidence,
                    }
                )
    return findings


@tool
def scan_column_for_pii(table_name: str, column_name: str) -> dict:
    """Scan sampled values from a specific column and classify PII types.

    Checks for: emails, US phone numbers, SSNs, credit card numbers,
    IPv4/IPv6 addresses, and date-of-birth patterns.

    Args:
        table_name: The table to scan.
        column_name: The column to scan.
    """
    try:
        conn = _get_connection()
        # Validate table and column exist
        cols = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
        col_names = [c["name"] for c in cols]
        if column_name not in col_names:
            conn.close()
            return {
                "error": f"Column '{column_name}' not found in '{table_name}'. "
                f"Available: {col_names}"
            }

        rows = conn.execute(
            f"SELECT \"{column_name}\" FROM '{table_name}' "
            f"WHERE \"{column_name}\" IS NOT NULL LIMIT ?",
            (SAMPLE_SIZE,),
        ).fetchall()
        conn.close()

        values = [str(r[column_name]) for r in rows if r[column_name] is not None]
        findings = _classify_values(values)

        # Summarize
        pii_types_found = {}
        for f in findings:
            pt = f["pii_type"]
            if pt not in pii_types_found:
                pii_types_found[pt] = {
                    "count": 0,
                    "max_confidence": 0.0,
                    "sample_matches": [],
                }
            pii_types_found[pt]["count"] += 1
            pii_types_found[pt]["max_confidence"] = max(
                pii_types_found[pt]["max_confidence"], f["confidence"]
            )
            if len(pii_types_found[pt]["sample_matches"]) < 3:
                pii_types_found[pt]["sample_matches"].append(f["matched_value"])

        return {
            "table": table_name,
            "column": column_name,
            "rows_scanned": len(values),
            "pii_found": bool(pii_types_found),
            "pii_types": pii_types_found,
        }
    except Exception as e:
        return {"error": f"Error scanning column: {e}"}


@tool
def scan_table_for_pii(table_name: str) -> dict:
    """Scan all columns in a table for PII and return a full report.

    Args:
        table_name: The table to scan.
    """
    try:
        conn = _get_connection()
        cols = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
        conn.close()

        if not cols:
            return {"error": f"Table '{table_name}' not found or has no columns."}

        column_reports = []
        high_risk_findings = []

        for col in cols:
            col_name = col["name"]
            report = scan_column_for_pii.invoke(
                {"table_name": table_name, "column_name": col_name}
            )
            column_reports.append(report)

            # Flag high-risk PII
            if isinstance(report, dict) and report.get("pii_types"):
                for pii_type, info in report["pii_types"].items():
                    if pii_type in ("ssn", "credit_card") or (
                        pii_type == "date_of_birth" and info["max_confidence"] > 0.6
                    ):
                        high_risk_findings.append(
                            {
                                "column": col_name,
                                "pii_type": pii_type,
                                "confidence": info["max_confidence"],
                            }
                        )

        return {
            "table": table_name,
            "columns_scanned": len(column_reports),
            "column_reports": column_reports,
            "high_risk_findings": high_risk_findings,
            "has_high_risk": bool(high_risk_findings),
        }
    except Exception as e:
        return {"error": f"Error scanning table: {e}"}


@tool
def detect_date_fields(table_name: str) -> list[dict]:
    """Identify columns in a table that contain date or datetime values.

    Checks both declared column types and actual sample data for date patterns.

    Args:
        table_name: The table to inspect.
    """
    try:
        conn = _get_connection()
        cols = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
        if not cols:
            conn.close()
            return [{"error": f"Table '{table_name}' not found."}]

        date_type_keywords = {"date", "datetime", "timestamp", "time"}
        date_pattern = re.compile(
            r"""(?x)
            \b
            (?:
                \d{4}[-/]\d{2}[-/]\d{2}  |
                \d{2}[-/]\d{2}[-/]\d{4}  |
                \d{4}-\d{2}-\d{2}T\d{2}:\d{2}
            )
            """
        )

        results = []
        for col in cols:
            col_name = col["name"]
            col_type = (col["type"] or "").lower()
            detected_by_type = any(kw in col_type for kw in date_type_keywords)

            # Sample data to check for date strings
            rows = conn.execute(
                f"SELECT \"{col_name}\" FROM '{table_name}' "
                f"WHERE \"{col_name}\" IS NOT NULL LIMIT 50",
            ).fetchall()
            date_matches = sum(
                1 for r in rows if date_pattern.search(str(r[col_name]))
            )
            detected_by_data = date_matches > len(rows) * 0.3 if rows else False

            # Also flag columns with "date", "dob", "birth" in name
            name_lower = col_name.lower()
            name_hints = any(
                kw in name_lower for kw in ("date", "dob", "birth", "created", "time")
            )

            could_be_dob = any(
                kw in name_lower for kw in ("dob", "birth", "born")
            )

            if detected_by_type or detected_by_data or name_hints:
                results.append(
                    {
                        "column": col_name,
                        "declared_type": col["type"],
                        "detected_by_type": detected_by_type,
                        "detected_by_data": detected_by_data,
                        "name_suggests_date": name_hints,
                        "could_be_dob": could_be_dob,
                        "sample_values": [
                            str(r[col_name]) for r in rows[:5]
                        ],
                    }
                )

        conn.close()
        return results if results else [{"message": "No date fields detected."}]
    except Exception as e:
        return [{"error": f"Error detecting date fields: {e}"}]
