"""Download the Hacker News dataset from Hugging Face and load it into SQLite."""

import argparse
import sqlite3
import sys

import datasets
import pandas as pd


DB_FILE = "hackernews.db"
TABLE_NAME = "posts"
DATASET_NAME = "OpenPipe/hacker-news"


def main():
    parser = argparse.ArgumentParser(
        description="Download Hacker News dataset and load into SQLite"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only load the first N rows (for faster testing)",
    )
    args = parser.parse_args()

    # Download dataset
    print(f"Downloading dataset '{DATASET_NAME}' from Hugging Face...")
    ds = datasets.load_dataset(DATASET_NAME, split="train")

    if args.limit:
        print(f"Limiting to first {args.limit} rows")
        ds = ds.select(range(min(args.limit, len(ds))))

    print(f"Converting {len(ds)} rows to dataframe...")
    df = ds.to_pandas()

    # Load into SQLite
    print(f"Loading into SQLite database '{DB_FILE}', table '{TABLE_NAME}'...")
    conn = sqlite3.connect(DB_FILE)
    df.to_sql(TABLE_NAME, conn, if_exists="replace", index=False)

    # Create index on type column
    print("Creating index on 'type' column...")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_type ON {TABLE_NAME}(type)")
    conn.commit()

    # Print summary
    total = conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
    print(f"\n{'='*60}")
    print(f"Total rows loaded: {total:,}")

    print(f"\nRow counts by type:")
    rows = conn.execute(
        f"SELECT type, COUNT(*) as cnt FROM {TABLE_NAME} GROUP BY type ORDER BY cnt DESC"
    ).fetchall()
    for type_val, count in rows:
        print(f"  {type_val}: {count:,}")

    # Show 3 sample records that have text content
    print(f"\n3 sample records with text content:")
    print("-" * 60)
    samples = conn.execute(
        f"SELECT id, type, title, text FROM {TABLE_NAME} "
        f"WHERE text IS NOT NULL AND text != '' LIMIT 3"
    ).fetchall()
    for row_id, row_type, title, text in samples:
        preview = (text[:200] + "...") if len(text) > 200 else text
        print(f"  id={row_id}  type={row_type}  title={title}")
        print(f"  text: {preview}\n")

    conn.close()
    print(f"Done. Database saved to '{DB_FILE}'.")


if __name__ == "__main__":
    main()
