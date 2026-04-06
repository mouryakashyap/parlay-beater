"""
Redis client + cache helpers.

Pattern: cache-aside
    1. Check Redis → hit? return immediately
    2. Miss → compute value → store in Redis with TTL → return

Why decode_responses=True?
    Returns str instead of bytes — easier to work with in Python.
"""

import json
import redis

from app.core.config import settings

# Single shared client — thread-safe in Redis-py
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)


def cache_get(key: str) -> dict | list | None:
    """Return deserialized value from Redis, or None on cache miss."""
    raw = redis_client.get(key)
    if raw is None:
        return None
    return json.loads(raw)


def cache_set(key: str, value: dict | list, ttl: int = settings.PREDICTION_CACHE_TTL) -> None:
    """Serialize value and store in Redis with TTL (seconds)."""
    redis_client.setex(key, ttl, json.dumps(value))


def cache_delete(key: str) -> None:
    """Invalidate a cache entry (e.g., when a prediction is updated)."""
    redis_client.delete(key)


def cache_delete_pattern(pattern: str) -> None:
    """
    Invalidate all keys matching a pattern.
    Use sparingly — SCAN is O(N) across all keys.
    Example: cache_delete_pattern("predictions:match:*")
    """
    keys = redis_client.keys(pattern)
    if keys:
        redis_client.delete(*keys)
