# backend/worker.py
import os
from dotenv import load_dotenv
import pandas as pd
from .dhan_client import DhanClient
from .main import background_task
from .redis_client import get_redis_client

def run_worker():
    # use for local testing/development 
    # load_dotenv(os.path.join(os.path.dirname(__file__), '.env.dev'))
    # use for docker deployment
    load_dotenv()
    redis_client = get_redis_client()

    CLIENT_ID = os.getenv('CLIENT_ID')
    ACCESS_TOKENS = os.getenv('ACCESS_TOKENS').split(',') if os.getenv('ACCESS_TOKENS') else []

    if not CLIENT_ID or not ACCESS_TOKENS:
        raise ValueError("CLIENT_ID or ACCESS_TOKENS not configured in environment")

    dh_clients = [DhanClient(CLIENT_ID, os.getenv(token)) for token in ACCESS_TOKENS]

    csv_path = os.path.join(os.path.dirname(__file__), 'Dependencies', 'my_instruments.csv')
    try:
        instruments = pd.read_csv(csv_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"The file '{csv_path}' was not found.")

    print("Starting background task...")
    background_task(redis_client, dh_clients, instruments)

if __name__ == "__main__":
    run_worker()