# AI Data Compliance

AI-powered analysis of Hacker News data using a LangGraph agent backed by ChatGPT.

## Dataset

This project uses the [OpenPipe/hacker-news](https://huggingface.co/datasets/OpenPipe/hacker-news) dataset from Hugging Face — a complete archive of all Hacker News posts and comments (~41M records). The dataset is free and public, no API key or Hugging Face account needed.

The data is loaded into a local SQLite database (`hackernews.db`) in a single table called `posts`.

### Schema

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Unique HN item ID |
| `type` | TEXT | Item type: `story`, `comment`, `job`, etc. |
| `by` | TEXT | Username of the author |
| `time` | TIMESTAMP | When the item was posted |
| `title` | TEXT | Title (stories and jobs only) |
| `text` | TEXT | Body text / comment content (HTML) |
| `url` | TEXT | Link URL (stories only) |
| `score` | REAL | Upvote score |
| `parent` | REAL | Parent item ID (comments only) |
| `top_level_parent` | INTEGER | Root-level parent story ID |
| `descendants` | REAL | Number of comments (stories only) |
| `kids` | TEXT | Child item IDs |
| `deleted` | INTEGER | Whether the item was deleted |
| `dead` | INTEGER | Whether the item was flagged dead |

### Breakdown by type (50k sample)

| Type | Count |
|------|-------|
| comment | 37,185 |
| story | 12,800 |
| job | 14 |

## Setup

```bash
pip install -r requirements.txt
```

Add your OpenAI API key to `secrets.txt`:
```
sk-proj-your-key-here
```

## Usage

**Load the dataset:**
```bash
python setup_data.py --limit 50000   # 50k rows for quick testing
python setup_data.py                  # full dataset (~41M rows)
```

**Run the chatbot agent (with PII tools):**
```bash
python agent.py
```

The agent can answer questions like:
- "Scan the database for PII"
- "What tables are in the database?"
- "Show me all date fields in the database"
- "Run a full PII audit"
- "Compare schema to last snapshot"

**Run the ambient PII monitor:**
```bash
python monitor.py                        # single run
python monitor.py --full-scan            # full PII scan of all tables
python monitor.py --loop                 # continuous monitoring (every 5 min)
python monitor.py --loop --interval 60   # continuous monitoring (every 60 sec)
```

Results are stored in the `pii_audit_log` table in the SQLite database.

## Project Structure

```
├── agent.py               # LangGraph chatbot with PII/DB tools
├── setup_data.py          # Dataset download and SQLite ingestion
├── monitor.py             # Ambient PII monitor entry point
├── requirements.txt       # Python dependencies
├── secrets.txt            # OpenAI API key (gitignored)
├── hackernews.db          # SQLite database (gitignored)
├── tools/
│   ├── __init__.py        # Exports ALL_TOOLS
│   ├── db_tools.py        # Database inspection tools
│   ├── pii_tools.py       # PII detection tools
│   └── schema_monitor.py  # Schema change detection tools
├── graphs/
│   └── pii_monitor.py     # LangGraph monitoring graph
├── schema_snapshots/      # Schema snapshot JSON files
│   └── .gitkeep
└── chat_history/          # Persisted chat sessions (gitignored)
```
