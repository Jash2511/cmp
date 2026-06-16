import asyncio
from database import get_db_pool, setup_supabase_table


async def initialize_database():
    print("Starting database initialization...")
    db_pool = await get_db_pool()

    await setup_supabase_table(db_pool)

    await db_pool.close()
    print("Initialization complete. You may now start the API and Worker.")


if __name__ == "__main__":
    asyncio.run(initialize_database())