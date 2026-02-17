---
name: setup-data
description: Run setup_data.py to download the Hacker News dataset from Hugging Face and load it into the local SQLite database (hackernews.db).
user-invocable: true
allowed-tools: Bash
---

Run the data setup script to download the Hacker News dataset and load it into SQLite.

Steps:

1. Install dependencies if needed:
   ```
   python3 -m pip install datasets pandas
   ```

2. Run the setup script with a default limit of 50,000 rows. If the user provided arguments, use those instead:
   ```
   python3 setup_data.py --limit 50000 $ARGUMENTS
   ```

3. After the script completes, verify the database was created by checking the file size of `hackernews.db`.

4. Report the summary back to the user (total rows, counts by type).
