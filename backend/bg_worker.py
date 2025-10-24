# backend/worker.py
import os
import redis
from dotenv import load_dotenv
import pandas as pd
import threading
from .dhan_client import DhanClient
from .main import background_task

def run_worker():
    # Load environment variables
    load_dotenv()
    
    # Initialize Redis client
    redis_client = redis.Redis(
        host=os.getenv('REDIS_HOST'),
        port=6379,
        db=0
    )
    try:
        if redis_client.ping():
            print("Redis connection successful!")
        else:
            print("Redis server did not respond to PING.")
    except redis.exceptions.ConnectionError as e:
        print(f"Could not connect to Redis: {e}")
        raise
    
    # Get credentials
    CLIENT_ID = os.getenv('CLIENT_ID')
    ACCESS_TOKENS = os.getenv('ACCESS_TOKENS').split(',') if os.getenv('ACCESS_TOKENS') else []
    if not CLIENT_ID or not ACCESS_TOKENS:
        raise ValueError("CLIENT_ID or ACCESS_TOKEN not found in .env file")
    
    # Initialize DhanClient instances
    dh_clients = [DhanClient(CLIENT_ID, os.getenv(token)) for token in ACCESS_TOKENS]
    
    # Load instruments
    csv_path = os.path.join(os.path.dirname(__file__), 'Dependencies', 'my_instruments.csv')
    try:
        instruments = pd.read_csv(csv_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"The file '{csv_path}' was not found.")
    
    # Start background task
    print("Starting background task...")
    thread = threading.Thread(target=background_task, args=(redis_client, dh_clients, instruments), daemon=True)
    thread.start()
    
    # Keep the script running
    thread.join()

if __name__ == "__main__":
    run_worker()