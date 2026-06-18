import asyncio
import multiprocessing
import uvicorn
from api_gateway import app as fastapi_app
from worker import moderation_worker
from init_db import initialize_database

def run_api_server():
    """
    Starts the FastAPI Uvicorn server in a separate process.
    """
    print("🚀 Starting API Gateway Server on http://127.0.0.1:8000")
    uvicorn.run(fastapi_app, host="127.0.0.1", port=8000, log_level="info")

def run_worker():
    """
    Starts the moderation worker in a separate process.
    """
    print("👷 Starting Moderation Worker...")
    try:
        asyncio.run(moderation_worker())
    except KeyboardInterrupt:
        print("🛑 Worker process interrupted.")

async def main():
    """
    Initializes the database and starts all services.
    """
    # 1. Initialize the database first
    print("--- Initializing Database ---")
    await initialize_database()
    print("--- Database is Ready ---")

    # 2. Create processes for the API server and the worker
    api_process = multiprocessing.Process(target=run_api_server)
    worker_process = multiprocessing.Process(target=run_worker)

    try:
        # 3. Start both processes
        api_process.start()
        worker_process.start()

        # 4. Wait for the processes to finish (they run forever until interrupted)
        api_process.join()
        worker_process.join()

    except KeyboardInterrupt:
        print("\n🛑 Shutting down all services...")
        # 5. Terminate processes on Ctrl+C
        api_process.terminate()
        worker_process.terminate()
        
        # Wait for processes to exit
        api_process.join()
        worker_process.join()
        
        print("--- All services shut down. ---")

if __name__ == "__main__":
    # 'spawn' is a safer way to create processes on macOS and Windows
    multiprocessing.set_start_method("spawn", force=True)
    asyncio.run(main())
