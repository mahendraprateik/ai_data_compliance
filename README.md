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
pip install datasets pandas langgraph langchain-openai
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

**Run the agent:**
```bash
python agent.py
```
