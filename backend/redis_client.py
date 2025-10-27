"""
Centralized Redis client factory.

Usage:
    from backend.redis_client import get_redis_client
    r = get_redis_client()
"""
from dotenv import load_dotenv
import os
import redis
from typing import Optional

load_dotenv()

_client: Optional[redis.Redis] = None

def get_redis_client() -> redis.Redis:
    global _client
    if _client is not None:
        return _client

    host = os.getenv("REDIS_HOST", "redis")
    port = int(os.getenv("REDIS_PORT", 6379))
    db = int(os.getenv("REDIS_DB", 0))
    password = os.getenv("REDIS_PASSWORD") or None
    decode_flag = os.getenv("REDIS_DECODE", "true").lower() in ("1", "true", "yes")

    _client = redis.Redis(
        host=host,
        port=port,
        db=db,
        password=password,
        decode_responses=decode_flag
    )

    try:
        if _client.ping():
            print(f"Redis connection successful ({host}:{port}, db={db})")
        else:
            print(f"Redis server at {host}:{port} did not respond to PING.")
    except Exception as exc:
        print(f"Warning: could not ping Redis at {host}:{port} — {exc}")

    return _client

def close_redis_client() -> None:
    global _client
    if _client is None:
        return
    try:
        _client.connection_pool.disconnect()
    except Exception:
        pass
    _client = None
