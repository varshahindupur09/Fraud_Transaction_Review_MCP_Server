# Fraud Transaction Review MCP Server

This project is a simple MCP server that connects Claude Desktop to a PostgreSQL database hosted in Google Cloud SQL.

The server exposes three MCP tools:

- `get_transaction`
- `list_flagged_transactions`
- `flag_for_review`

The purpose of the project is to demonstrate how an MCP client such as Claude Desktop can call Python functions that read from and write to a database.

---

## Project Structure

```text
MCPServer/
│
├── server.py
├── db.py
├── .env
├── requirements.txt
└── venv/
```

### `server.py`

Contains the MCP server and defines the tools that Claude can call.

### `db.py`

Handles the connection to PostgreSQL through Google Cloud SQL.

### `.env`

Stores database credentials and Cloud SQL configuration.

---

# 1. Create the Project Folder

Create a folder for the project.

```bash
mkdir MCPServer
cd MCPServer
```

---

# 2. Create a Python Virtual Environment

Create the virtual environment:

```bash
python3 -m venv venv
```

Activate it on macOS/Linux:

```bash
source venv/bin/activate
```

After activation, the terminal should show something similar to:

```text
(venv) user@MacBook MCPServer %
```

---

# 3. Install Required Packages

Install the required Python packages:

```bash
pip install "cloud-sql-python-connector[asyncpg]" asyncpg python-dotenv mcp
```

Optionally create a `requirements.txt`:

```bash
pip freeze > requirements.txt
```

---

# 4. Create the `.env` File

Create a file named:

```text
.env
```

Add the following values:

```env
INSTANCE_CONNECTION_NAME=your-project:your-region:your-instance
DB_USER=your_database_user
DB_PASS=your_database_password
DB_NAME=your_database_name
```

Example:

```env
INSTANCE_CONNECTION_NAME=my-project:us-central1:fraud-db
DB_USER=postgres
DB_PASS=myPassword
DB_NAME=transactions_db
```

Do not commit `.env` to GitHub.

Add this to `.gitignore`:

```text
.env
venv/
__pycache__/
```

---

# 5. Database Connection

Create `db.py`.

```python
import os
from contextlib import asynccontextmanager

import asyncpg
from dotenv import load_dotenv
from google.cloud.sql.connector import create_async_connector


# Load environment variables from .env
load_dotenv()


# Database configuration
INSTANCE_CONNECTION_NAME = os.environ["INSTANCE_CONNECTION_NAME"]
DB_USER = os.environ["DB_USER"]
DB_PASS = os.environ["DB_PASS"]
DB_NAME = os.environ["DB_NAME"]


@asynccontextmanager
async def get_connection():
    """
    Open a connection to PostgreSQL through Google Cloud SQL.

    The connection is automatically closed after the calling
    function finishes using it.
    """

    # Create an asynchronous Google Cloud SQL connector.
    connector = await create_async_connector()

    conn = None

    try:
        # Open PostgreSQL connection using asyncpg.
        conn = await connector.connect_async(
            INSTANCE_CONNECTION_NAME,
            "asyncpg",
            user=DB_USER,
            password=DB_PASS,
            db=DB_NAME,
        )

        # Give the connection to the calling function.
        yield conn

    finally:
        # Close PostgreSQL connection.
        if conn is not None:
            await conn.close()

        # Close Cloud SQL connector.
        await connector.close_async()
```

The important part is:

```python
async with get_connection() as conn:
```

This means:

```text
Open database connection
        ↓
Use connection
        ↓
Run query
        ↓
Close connection
```

The cleanup happens automatically.

---

# 6. Create the MCP Server

Create `server.py`.

```python
from mcp.server.fastmcp import FastMCP

from db import get_connection


# Create MCP server
mcp = FastMCP("transaction-mcp-server")


@mcp.tool()
async def get_transaction(transaction_id: int) -> dict:
    """
    Fetch one transaction using its transaction ID.
    """

    async with get_connection() as conn:
        row = await conn.fetchrow(
            '''
            SELECT id, "Time", "Amount", "Class"
            FROM transactions
            WHERE id = $1
            ''',
            transaction_id,
        )

    if row is None:
        return {
            "error": f"No transaction found with id {transaction_id}"
        }

    return dict(row)


@mcp.tool()
async def list_flagged_transactions(limit: int = 10) -> list[dict]:
    """
    Return transactions that are already marked as fraud.

    Class = 1 means fraudulent transaction.
    """

    async with get_connection() as conn:
        rows = await conn.fetch(
            '''
            SELECT id, "Time", "Amount"
            FROM transactions
            WHERE "Class" = 1
            LIMIT $1
            ''',
            limit,
        )

    return [dict(row) for row in rows]


@mcp.tool()
async def flag_for_review(transaction_id: int) -> dict:
    """
    Add a transaction to the pending_review table.

    This does not modify the original transaction.
    It only records the transaction for later human review.
    """

    async with get_connection() as conn:

        # Check whether the transaction exists.
        exists = await conn.fetchval(
            """
            SELECT 1
            FROM transactions
            WHERE id = $1
            """,
            transaction_id,
        )

        if not exists:
            return {
                "error": f"No transaction found with id {transaction_id}"
            }

        # Add transaction to review queue.
        await conn.execute(
            """
            INSERT INTO pending_review (transaction_id)
            VALUES ($1)
            """,
            transaction_id,
        )

    return {
        "status": "flagged for review",
        "transaction_id": transaction_id,
    }


# Start MCP server when server.py is executed.
if __name__ == "__main__":
    mcp.run()
```

---

# 7. Understanding the Three MCP Tools

## `get_transaction`

Example request:

```text
Get transaction with id 1
```

Claude can call:

```python
get_transaction(1)
```

The database query is:

```sql
SELECT id, "Time", "Amount", "Class"
FROM transactions
WHERE id = 1;
```

---

## `list_flagged_transactions`

Example request:

```text
Show me 10 fraudulent transactions.
```

Claude can call:

```python
list_flagged_transactions(10)
```

The query retrieves transactions where:

```text
Class = 1
```

---

## `flag_for_review`

Example request:

```text
Flag transaction 123 for review.
```

The tool first verifies that transaction `123` exists.

It then inserts the ID into:

```text
pending_review
```

The original transaction is not changed.

---

# 8. How the Application Works

```text
Claude Desktop
      |
      v
MCP Server
 server.py
      |
      v
MCP Tool
      |
      v
db.py
      |
      v
Google Cloud SQL Connector
      |
      v
PostgreSQL
      |
      v
transactions table
```

For example:

```text
User:
"Get transaction 1"

        ↓

Claude

        ↓

MCP tool:
get_transaction(1)

        ↓

db.py creates database connection

        ↓

PostgreSQL executes query

        ↓

Result returned to MCP

        ↓

Claude displays result
```

---

# 9. Testing the Database Without MCP

Before testing Claude, it can be useful to test the database connection directly.

Create:

```text
test_db.py
```

Add:

```python
import asyncio

from db import get_connection


async def main():

    async with get_connection() as conn:

        row = await conn.fetchrow(
            '''
            SELECT id, "Time", "Amount", "Class"
            FROM transactions
            WHERE id = $1
            ''',
            1,
        )

        print(row)


asyncio.run(main())
```

Run:

```bash
python test_db.py
```

If the connection works, a database row should be printed.

---

# 10. Configure Claude Desktop

Claude Desktop should be configured to launch the MCP server using the Python executable inside the project's virtual environment.

Example configuration:

```json
{
  "mcpServers": {
    "transaction-mcp-server": {
      "command": "/Users/USERNAME/Workspace/MCPServer/venv/bin/python",
      "args": [
        "/Users/USERNAME/Workspace/MCPServer/server.py"
      ]
    }
  }
}
```

Replace `USERNAME` and the project path with the actual location of the project.

---

# 11. Restart Claude Desktop

After changing MCP server code or configuration, completely quit Claude Desktop and reopen it.

This is important because Claude Desktop starts the MCP server as a separate Python process.

---

# 12. Check Whether the MCP Server Is Running

Run:

```bash
ps aux | grep server.py
```

A running MCP server may appear similar to:

```text
/Users/USERNAME/Workspace/MCPServer/venv/bin/python \
/Users/USERNAME/Workspace/MCPServer/server.py
```

If only the following appears:

```text
grep server.py
```

then the MCP server is not running.

---

# 13. Stop Old MCP Server Processes

During development, an old copy of the MCP server may remain running.

Check running processes:

```bash
ps aux | grep server.py
```

Kill a specific process:

```bash
kill -9 PID
```

Example:

```bash
kill -9 7637
```

To kill all instances of this MCP server:

```bash
pkill -f "/Users/USERNAME/Workspace/MCPServer/server.py"
```

If the command returns:

```text
kill: kill 7637 failed: no such process
```

that means the process had already stopped.

It is not necessarily an error with the MCP application.

---

# 14. Errors Encountered During Development

Several errors occurred while originally using `asyncpg.create_pool()` together with the Google Cloud SQL Connector.

## Error 1

```text
get_conn() got an unexpected keyword argument 'loop'
```

The original code contained a custom function similar to:

```python
async def get_conn():
    ...
```

and passed it to:

```python
asyncpg.create_pool(
    connect=get_conn
)
```

However, `asyncpg` may internally call the custom connection function with additional arguments such as:

```text
loop
connection_class
record_class
```

Therefore the function was not compatible with the way `asyncpg.create_pool()` called it.

---

## Error 2

```text
get_conn() takes 0 positional arguments but 1 was given
```

The connection callback was changed, but `asyncpg` still passed positional arguments to the custom function.

For example:

```python
async def get_conn():
```

could not accept the arguments being passed internally by the pool.

Changing it to:

```python
async def get_conn(*args, **kwargs):
```

avoided this particular error but did not solve the underlying event-loop problem.

---

## Error 3

```text
Running event loop does not match 'connector._loop'
```

This was the most important error.

The original code used:

```python
Connector(loop=asyncio.get_running_loop())
```

The connector therefore became associated with one particular Python event loop.

Later, when MCP or `asyncpg` attempted to use the connector from another event-loop context, the connector detected that the loops did not match.

The approximate problem was:

```text
MCP event loop
      |
      v
Connector created
      |
      v
asyncpg pool
      |
      v
another async context/event loop
      |
      X
Event-loop mismatch
```

---

# 15. Original Problematic Design

The original `db.py` was approximately:

```python
_connector = None
_pool = None


async def get_pool():

    global _connector, _pool

    if _pool is None:

        _connector = Connector(
            loop=asyncio.get_running_loop()
        )

        async def get_conn(*args, **kwargs):

            return await _connector.connect_async(
                INSTANCE_CONNECTION_NAME,
                "asyncpg",
                user=DB_USER,
                password=DB_PASS,
                db=DB_NAME,
            )

        _pool = await asyncpg.create_pool(
            min_size=1,
            max_size=5,
            connect=get_conn,
        )

    return _pool
```

The combination of:

```text
global Connector
+
global asyncpg pool
+
explicit event loop
+
MCP asynchronous execution
```

made the connection lifecycle difficult to control.

---

# 16. Solution

The simpler solution was to remove the custom `asyncpg` pool temporarily.

Instead of:

```text
MCP
 ↓
asyncpg pool
 ↓
custom callback
 ↓
Cloud SQL connector
 ↓
PostgreSQL
```

the project now uses:

```text
MCP
 ↓
create_async_connector()
 ↓
connect_async()
 ↓
PostgreSQL
```

Each tool obtains a connection using:

```python
async with get_connection() as conn:
```

and then automatically closes it afterward.

This avoids keeping a connector tied to an old event loop.

---

# 17. Why Pooling Was Removed

Connection pooling is useful in larger production applications because it avoids repeatedly opening new database connections.

However, this project is currently focused on getting the MCP integration working correctly.

The simpler design makes it easier to:

- understand the async behavior;
- isolate database errors;
- avoid event-loop conflicts;
- test MCP tools individually;
- confirm that Cloud SQL authentication works.

Pooling can be added later once the basic MCP server is stable.

---

# 18. Important `asyncpg` Methods

The project uses four common `asyncpg` methods.

### `fetchrow()`

Returns one database row.

```python
row = await conn.fetchrow(...)
```

Used by:

```text
get_transaction
```

---

### `fetch()`

Returns multiple database rows.

```python
rows = await conn.fetch(...)
```

Used by:

```text
list_flagged_transactions
```

---

### `fetchval()`

Returns one value.

```python
exists = await conn.fetchval(...)
```

Used to check whether a transaction exists.

---

### `execute()`

Runs a database operation without expecting rows to be returned.

```python
await conn.execute(...)
```

Used when inserting a transaction into `pending_review`.

---

# 19. What `$1` Means

Queries use parameters such as:

```sql
WHERE id = $1
```

`$1` represents the first value supplied after the SQL query.

Example:

```python
await conn.fetchrow(
    "SELECT * FROM transactions WHERE id = $1",
    transaction_id,
)
```

If:

```python
transaction_id = 25
```

the query logically behaves like:

```sql
SELECT *
FROM transactions
WHERE id = 25;
```

Using parameters such as `$1` is safer than manually inserting values into SQL strings.

---

# 20. Suggested Testing Order

During development, test the project in this order:

```text
1. Activate virtual environment

        ↓

2. Check .env values

        ↓

3. Run test_db.py

        ↓

4. Confirm database query works

        ↓

5. Configure Claude Desktop

        ↓

6. Restart Claude Desktop

        ↓

7. Check server process

        ↓

8. Ask Claude:
   "Get transaction with id 1"

        ↓

9. Test the other MCP tools
```

---

# 21. Example MCP Requests

Once the server is connected to Claude Desktop, try:

```text
Get transaction with id 1.
```

Then:

```text
Show me 5 fraudulent transactions.
```

Then:

```text
Flag transaction 1 for human review.
```

Claude should recognize the appropriate MCP tool and call it automatically.

---

# Current MCP Tools

| Tool | Purpose |
|---|---|
| `get_transaction` | Retrieve one transaction by ID |
| `list_flagged_transactions` | Retrieve transactions where `Class = 1` |
| `flag_for_review` | Add a transaction to the human-review queue |

---

# Summary

This project demonstrates the full flow:

```text
Natural-language request
        ↓
Claude Desktop
        ↓
MCP Tool
        ↓
Python
        ↓
Google Cloud SQL Connector
        ↓
PostgreSQL
        ↓
Database result
        ↓
Claude Desktop
```

The main technical issue encountered during development was an asynchronous event-loop mismatch caused by combining a long-lived Google Cloud SQL connector with a custom `asyncpg` connection pool.

The simplified implementation uses an asynchronous context manager and creates the Cloud SQL connection within the same asynchronous lifecycle as the MCP tool, making the behavior easier to understand and debug.