"""Redis control-plane helpers: rate limits, SSE pub/sub, queue relay.

When ``MYMLFW_REDIS_URL`` is unset or connect fails, callers keep in-memory
fallbacks. Bind the live client from API lifespan via ``bind_redis``.
"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator

# Process-bound clients set by API lifespan (None → in-memory paths).
_redis: Any | None = None  # redis.asyncio
_redis_sync: Any | None = None  # redis.Redis (sync rate limits)

SSE_CHANNEL = "mymlfw:sse"
QUEUE_RELAY_KEY = "mymlfw:queue:relay"
IDEMPOTENCY_PREFIX = "mymlfw:idem:"
LLM_RATE_PREFIX = "mymlfw:rl:llm:"
KAGGLE_RATE_PREFIX = "mymlfw:rl:kaggle:"


def bind_redis(client: Any | None, sync_client: Any | None = None) -> None:
    global _redis, _redis_sync
    _redis = client
    if sync_client is not None or client is None:
        _redis_sync = sync_client


def get_redis() -> Any | None:
    return _redis


def get_redis_sync() -> Any | None:
    return _redis_sync


def clear_redis_for_tests() -> None:
    bind_redis(None, None)


async def close_redis(
    client: Any | None = None, sync_client: Any | None = None
) -> None:
    target = client if client is not None else _redis
    sync = sync_client if sync_client is not None else _redis_sync
    if target is not None:
        try:
            await target.aclose()
        except Exception:
            try:
                await target.close()
            except Exception:
                pass
    if sync is not None:
        try:
            sync.close()
        except Exception:
            pass
    if target is _redis or sync is _redis_sync:
        bind_redis(None, None)


async def connect_redis(url: str) -> tuple[Any, Any]:
    """Open async + sync Redis clients and ping. Raises on failure."""
    import redis as redis_sync
    from redis.asyncio import Redis

    client = Redis.from_url(url, decode_responses=False)
    await client.ping()
    sync_client = redis_sync.Redis.from_url(url, decode_responses=False)
    sync_client.ping()
    return client, sync_client


# --- Rate limits (sync Redis — LLM/Kaggle call sites are sync) --------------


def llm_rate_limit_redis(
    *,
    org_id: str,
    project_id: str,
    tool: str,
    per_minute: int = 6,
) -> bool | None:
    """Redis sliding window. ``None`` → Redis unset (use memory); False → deny."""
    r = get_redis_sync()
    if r is None:
        return None
    key = f"{LLM_RATE_PREFIX}{org_id}:{project_id}:{tool}"
    now = time.time()
    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, now - 60.0)
    pipe.zcard(key)
    pipe.zadd(key, {f"{now}:{tool}:{now}".encode(): now})
    pipe.expire(key, 120)
    results = pipe.execute()
    count = int(results[1] or 0)
    return count < per_minute


def kaggle_rate_limit_redis(
    client_ip: str, *, per_minute: int = 30
) -> bool | None:
    """Redis sliding window. ``None`` → Redis unset (use memory); False → deny."""
    r = get_redis_sync()
    if r is None:
        return None
    key = f"{KAGGLE_RATE_PREFIX}{client_ip}"
    now = time.time()
    pipe = r.pipeline()
    pipe.zremrangebyscore(key, 0, now - 60.0)
    pipe.zcard(key)
    pipe.zadd(key, {f"{now}".encode(): now})
    pipe.expire(key, 120)
    results = pipe.execute()
    count = int(results[1] or 0)
    return count < per_minute


# --- SSE pub/sub -------------------------------------------------------------


async def publish_sse_event(
    *,
    event: str,
    data: dict[str, Any],
    event_id: int | None = None,
    channel: str = SSE_CHANNEL,
) -> int:
    """Publish one SSE payload for multi-worker fan-out. Returns receivers."""
    r = get_redis()
    if r is None:
        return 0
    payload = json.dumps(
        {"id": event_id, "event": event, "data": data},
        default=str,
    )
    return int(await r.publish(channel, payload.encode("utf-8")))


async def iter_sse_from_redis(
    *,
    channel: str = SSE_CHANNEL,
    stop_after_s: float | None = None,
) -> AsyncIterator[str]:
    """Yield SSE chunks from Redis pub/sub (plus keepalive pings)."""
    r = get_redis()
    if r is None:
        return
        yield  # pragma: no cover — make this an async generator
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)
    started = time.time()
    try:
        while True:
            if stop_after_s is not None and (time.time() - started) >= stop_after_s:
                break
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if message is None:
                yield ": ping\n\n"
                continue
            raw = message.get("data")
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            eid = obj.get("id")
            ev = obj.get("event") or "message"
            data = obj.get("data")
            body = json.dumps(data, default=str)
            chunk = ""
            if eid is not None:
                chunk += f"id: {eid}\n"
            chunk += f"event: {ev}\ndata: {body}\n\n"
            yield chunk
    finally:
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
        except Exception:
            pass


# --- Worker queue relay ------------------------------------------------------


async def enqueue_queue_relay(payload: dict[str, Any]) -> None:
    """LPUSH worker relay envelope when Redis is up (no-op otherwise)."""
    r = get_redis()
    if r is None:
        return
    await r.lpush(QUEUE_RELAY_KEY, json.dumps(payload, default=str).encode())


async def pop_queue_relay(timeout_s: int = 1) -> dict[str, Any] | None:
    r = get_redis()
    if r is None:
        return None
    item = await r.brpop(QUEUE_RELAY_KEY, timeout=timeout_s)
    if not item:
        return None
    _, raw = item
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return json.loads(raw)
