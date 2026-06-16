import asyncpg
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
async def get_db_pool():
    """Create and returns the connection pool."""
    return await asyncpg.create_pool(SUPABASE_URL,ssl="require",statement_cache_size=0,command_timeout=60)

async def setup_supabase_table(pool):
    """Create and initialize the database tables IF they don't exist."""
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS platforms(
                id SERIAL PRIMARY KEY,
                name VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE
            )
        ''')


        await conn.execute('''
            CREATE TABLE IF NOT EXISTS moderation_results (
                request_id UUID PRIMARY KEY,
                platform_id INTEGER REFERENCES platforms(id),
                reason TEXT,
                post_category VARCHAR(20),
                confidence_score FLOAT,
                flagged_keywords TEXT[],
                completed_at TIMESTAMP
            )
        ''')
        print("SUPABASE tables are ready!")

async def register_platform(pool, name: str, email: str):
    """
    Registers a new platform in the database.
    Returns the new platform's ID.
    """
    async with pool.acquire() as conn:
        new_id = await conn.fetchval('''
            INSERT INTO platforms (name, email)
            VALUES ($1, $2)
            ON CONFLICT (name) DO NOTHING
            RETURNING id;
        ''', name, email)
        return new_id

async def get_platform_mapping(pool):
    """Fetches platforms to create a dictionary: {'twitter': 1, 'facebook': 2}"""
    mapping = {}
    async with pool.acquire() as conn:
        rows = await conn.fetch('SELECT id, name FROM platforms')

        for row in rows:
            mapping[row['id']] = row['name']

        print("Platform mapping is ready!")
    return mapping

async def get_platform_by_id(pool, platform_id):
    """Fetches a single platform by ID."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT name FROM platforms WHERE id = $1', platform_id)
        if row:
            return row['name']
        return None

async def get_platform_email_by_id(pool, platform_id):
    """Fetches a single platform email by ID."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT email FROM platforms WHERE id = $1', platform_id)
        if row:
            return row['email']
        return None

async def save_request_result(pool, request_id, platform_id, reason, post_category ,confidence_score,flagged_keywords):
    """Saves the final moderation result to Supabase."""
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO moderation_results (request_id, platform_id, reason, post_category,confidence_score,flagged_keywords, completed_at)
            VALUES ($1, $2, $3, $4, $5 , $6 , $7)
        ''', request_id , platform_id , reason , post_category , confidence_score , flagged_keywords , datetime.utcnow())
    print(f"Result '{post_category}' saved to Supabase for request '{request_id}")