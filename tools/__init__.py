"""PII detection and database monitoring tools."""

from tools.db_tools import (
    get_all_tables,
    get_table_schema,
    sample_table_data,
    run_read_only_query,
    get_database_metadata,
)
from tools.pii_tools import (
    scan_column_for_pii,
    scan_table_for_pii,
    detect_date_fields,
)
from tools.schema_monitor import (
    snapshot_schema,
    compare_schema_snapshots,
    detect_schema_changes,
)

ALL_TOOLS = [
    get_all_tables,
    get_table_schema,
    sample_table_data,
    run_read_only_query,
    get_database_metadata,
    scan_column_for_pii,
    scan_table_for_pii,
    detect_date_fields,
    snapshot_schema,
    compare_schema_snapshots,
    detect_schema_changes,
]
