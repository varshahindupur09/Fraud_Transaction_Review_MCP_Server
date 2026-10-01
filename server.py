# FastMCP is what lets us create MCP tools that Claude/Cursor can discover and call.
from mcp.server.fastmcp import FastMCP

# Import our database connection function
from db import get_connection

# Create the MCP server with name which is mainly an identifier for the server.
mcp = FastMCP("transaction-mcp-server")


@mcp.tool()
async def get_transaction(transaction_id: int) -> dict:
    """Fetch a single transaction by its id."""

    async with get_connection() as conn:
        # Ask PostgreSQL for one transaction.
        # $1 is a placeholder.
        # If transaction_id = 1, asyncpg safely substitutes 1 for $1.
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

    # asyncpg returns something called a Record. Convert it into a regular Python dictionary so Claude/MCP can easily understand it.
    return dict(row)


@mcp.tool()
async def list_flagged_transactions(limit: int = 10) -> list[dict]:
    """List transactions already labeled as fraud."""

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
    Flag a transaction for human review.
    Important:
    This does NOT change the original transaction.
    It just adds the transaction ID to a review queue.
    """

    async with get_connection() as conn:
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


if __name__ == "__main__":
    mcp.run()