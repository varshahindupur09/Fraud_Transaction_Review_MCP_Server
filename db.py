import os

# This helps us create a "context manager"
# so the database connection opens and closes automatically.
from contextlib import asynccontextmanager

import asyncpg

# Reads values from your .env file
from dotenv import load_dotenv

# Google Cloud SQL helper for async database connections
from google.cloud.sql.connector import create_async_connector

# Load variables from .env
load_dotenv()

# Read database settings from the environment.
INSTANCE_CONNECTION_NAME = os.environ["INSTANCE_CONNECTION_NAME"]
DB_USER = os.environ["DB_USER"]
DB_PASS = os.environ["DB_PASS"]
DB_NAME = os.environ["DB_NAME"]

# This function creates a database connection.
# @asynccontextmanager allows us to later write:
# async with get_connection() as conn: and Python will automatically clean up the connection afterward.
@asynccontextmanager
async def get_connection():
    # Create Google's Cloud SQL connector.
    # It is "Creatinf a secure bridge between my Python program and my PostgreSQL database in Google Cloud."
    connector = await create_async_connector()

    conn = None

    try:
        # Open a PostgreSQL connection through Google Cloud SQL. Which Cloud SQL instance should we connect to? Which PostgreSQL Python driver should we use? Database login information
        conn: asyncpg.Connection = await connector.connect_async(
            INSTANCE_CONNECTION_NAME,
            "asyncpg",
            user=DB_USER,
            password=DB_PASS,
            db=DB_NAME,
        )

        # Give the open database connection back to whatever function requested it.
        yield conn

    finally:
        # Once the MCP tool finishes using the database, close the PostgreSQL connection and the Google Cloud SQL connector.
        if conn is not None:
            await conn.close()

        await connector.close_async()