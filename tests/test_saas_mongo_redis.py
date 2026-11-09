"""Phase-1 durability: Mongo project data + Redis control plane."""

from __future__ import annotations

import os
import uuid

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")
pytest.importorskip("redis")


def _mongo_uri() -> str:
    return os.environ.get("MYMLFW_MONGO_URI", "").strip()


def _redis_uri() -> str:
    return os.environ.get(
        "MYMLFW_REDIS_URL", "redis://127.0.0.1:6379/0"
    ).strip()


async def _mongo_available(uri: str) -> bool:
    if not uri:
        return False
    try:
        from mymlfw.saas.db.client import create_saas_mongo_client

        client = create_saas_mongo_client(uri)
        await client.admin.command("ping")
        await client.close()
        return True
    except Exception:
        return False


async def _redis_available(uri: str) -> bool:
    if not uri:
        return False
    try:
        from mymlfw.saas.redis_control import connect_redis, close_redis

        client, sync_client = await connect_redis(uri)
        await close_redis(client, sync_client)
        return True
    except Exception:
        return False


@pytest.mark.asyncio
async def test_brain_routes_use_memory_when_mongo_unset():
    from httpx import ASGITransport, AsyncClient

    from mymlfw.api.app import create_app
    from mymlfw.api.auth import seed_dev_personas
    from mymlfw.api.settings import Settings
    from mymlfw.saas.brain_store import BRAIN_STORE

    seed_dev_personas()
    before = len(BRAIN_STORE.projects)
    app = create_app(Settings(env="dev", mongo_uri="", redis_url=""))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/v1/auth/login",
            json={"email": "owner@localhost", "password": "devpassword"},
            headers={"X-Mymlfw-Client-Version": "0.2.0"},
        )
        token = login.json()["access_token"]
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Mymlfw-Client-Version": "0.2.0",
        }
        gone = await client.post("/v1/studio/ensure-demo", headers=headers)
        assert gone.status_code == 404
        created = await client.post(
            "/v1/projects",
            headers={**headers, "Idempotency-Key": "mem-create-1"},
            json={
                "name": "Memory fixture",
                "kind": "standalone",
                "goals": [
                    {
                        "title": "CV floor",
                        "kind": "notebook_score",
                        "metric_key": "cv_mean",
                        "threshold": 0.30,
                        "direction": "maximize",
                    }
                ],
            },
        )
        assert created.status_code == 200, created.text
        assert len(BRAIN_STORE.projects) >= before + 1


@pytest.mark.asyncio
async def test_mongo_project_survives_new_app_instance():
    uri = _mongo_uri() or "mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true"
    if not await _mongo_available(uri):
        pytest.skip("mongo unavailable")

    from httpx import ASGITransport, AsyncClient

    from mymlfw.api.app import create_app
    from mymlfw.api.auth import seed_dev_personas
    from mymlfw.api.settings import Settings
    from mymlfw.saas.brain_store import BRAIN_STORE

    db_name = f"mymlfw_test_{uuid.uuid4().hex[:10]}"
    seed_dev_personas()
    memory_count = len(BRAIN_STORE.projects)

    settings = Settings(
        env="dev",
        mongo_uri=uri,
        mongo_db=db_name,
        redis_url="",
    )
    app1 = create_app(settings)
    transport1 = ASGITransport(app=app1)
    async with app1.router.lifespan_context(app1):
        async with AsyncClient(transport=transport1, base_url="http://test") as client:
            login = await client.post(
                "/v1/auth/login",
                json={"email": "owner@localhost", "password": "devpassword"},
                headers={"X-Mymlfw-Client-Version": "0.2.0"},
            )
            token = login.json()["access_token"]
            headers = {
                "Authorization": f"Bearer {token}",
                "X-Mymlfw-Client-Version": "0.2.0",
            }
            created = await client.post(
                "/v1/projects",
                headers={**headers, "Idempotency-Key": "mongo-survives-1"},
                json={
                    "name": "Durable fixture",
                    "kind": "standalone",
                    "goals": [
                        {
                            "title": "CV floor",
                            "kind": "notebook_score",
                            "metric_key": "cv_mean",
                            "threshold": 0.30,
                            "direction": "maximize",
                        }
                    ],
                },
            )
            assert created.status_code == 200, created.text
            project_id = created.json()["id"]
            # Production path must not deepen the in-memory hole.
            assert len(BRAIN_STORE.projects) == memory_count

            dash = await client.get(
                f"/v1/projects/{project_id}/dashboard", headers=headers
            )
            assert dash.status_code == 200
            assert "progress_pct" in dash.json()["header"]

    # Fresh app / lifespan — same Mongo DB still lists the project.
    app2 = create_app(settings)
    transport2 = ASGITransport(app=app2)
    async with app2.router.lifespan_context(app2):
        async with AsyncClient(transport=transport2, base_url="http://test") as client:
            login = await client.post(
                "/v1/auth/login",
                json={"email": "owner@localhost", "password": "devpassword"},
                headers={"X-Mymlfw-Client-Version": "0.2.0"},
            )
            token = login.json()["access_token"]
            headers = {
                "Authorization": f"Bearer {token}",
                "X-Mymlfw-Client-Version": "0.2.0",
            }
            listed = await client.get("/v1/projects", headers=headers)
            assert listed.status_code == 200
            ids = [p["id"] for p in listed.json()["projects"]]
            assert project_id in ids

    # Cleanup test DB.
    from mymlfw.saas.db.client import create_saas_mongo_client

    client = create_saas_mongo_client(uri)
    await client.drop_database(db_name)
    await client.close()


@pytest.mark.asyncio
async def test_redis_idempotency_survives_store_instance():
    uri = _redis_uri()
    if not await _redis_available(uri):
        pytest.skip("redis unavailable")

    from mymlfw.api.idempotency import RedisIdempotencyStore
    from mymlfw.saas.redis_control import close_redis, connect_redis

    client, sync_client = await connect_redis(uri)
    try:
        store_a = RedisIdempotencyStore(client, ttl_s=60)
        key = f"POST:/v1/projects/test:idem-{uuid.uuid4().hex}"
        assert await store_a.set_in_progress(key) is True
        await store_a.set_result(
            key,
            status_code=200,
            body=b'{"ok":true}',
            headers={"content-type": "application/json"},
        )
        # New store instance (simulates API process reload) still replays.
        store_b = RedisIdempotencyStore(client, ttl_s=60)
        replay = await store_b.get(key)
        assert replay is not None
        assert replay["status"] == "DONE"
        assert replay["body"] == b'{"ok":true}'
        # 5xx must not stick.
        key5 = f"POST:/v1/projects/test:idem5-{uuid.uuid4().hex}"
        assert await store_a.set_in_progress(key5) is True
        await store_a.set_result(
            key5, status_code=500, body=b"fail", headers={}
        )
        assert await store_b.get(key5) is None
        await store_a.clear(key)
    finally:
        await close_redis(client, sync_client)


@pytest.mark.asyncio
async def test_redis_rate_limits_and_sse_pubsub():
    uri = _redis_uri()
    if not await _redis_available(uri):
        pytest.skip("redis unavailable")

    from mymlfw.saas import redis_control as rc

    client, sync_client = await rc.connect_redis(uri)
    rc.bind_redis(client, sync_client)
    try:
        org = f"org_test{uuid.uuid4().hex[:16]}"
        prj = f"prj_test{uuid.uuid4().hex[:16]}"
        # First five allowed, sixth trips at per_minute=5.
        for _ in range(5):
            assert (
                rc.llm_rate_limit_redis(
                    org_id=org, project_id=prj, tool="embed", per_minute=5
                )
                is True
            )
        assert (
            rc.llm_rate_limit_redis(
                org_id=org, project_id=prj, tool="embed", per_minute=5
            )
            is False
        )
        ip = f"203.0.113.{uuid.uuid4().int % 200}"
        assert rc.kaggle_rate_limit_redis(ip, per_minute=2) is True
        assert rc.kaggle_rate_limit_redis(ip, per_minute=2) is True
        assert rc.kaggle_rate_limit_redis(ip, per_minute=2) is False

        received: list[str] = []

        async def _listen():
            async for chunk in rc.iter_sse_from_redis(stop_after_s=1.5):
                if "train_strip" in chunk:
                    received.append(chunk)
                    break

        import asyncio

        listener = asyncio.create_task(_listen())
        await asyncio.sleep(0.1)
        n = await rc.publish_sse_event(
            event="train_strip",
            data={"fold": "1/5"},
            event_id=42,
        )
        assert n >= 0
        await listener
        assert received
        assert "train_strip" in received[0]

        await rc.enqueue_queue_relay({"job": "test", "id": uuid.uuid4().hex})
        popped = await rc.pop_queue_relay(timeout_s=1)
        assert popped is not None
        assert popped["job"] == "test"
    finally:
        await rc.close_redis(client, sync_client)


@pytest.mark.asyncio
async def test_api_lifespan_binds_redis_when_url_set():
    uri = _redis_uri()
    if not await _redis_available(uri):
        pytest.skip("redis unavailable")

    from mymlfw.api.app import create_app
    from mymlfw.api.idempotency import RedisIdempotencyStore
    from mymlfw.api.settings import Settings

    app = create_app(Settings(env="dev", mongo_uri="", redis_url=uri))
    async with app.router.lifespan_context(app):
        assert app.state.redis is not None
        assert app.state.redis_sync is not None
        assert isinstance(app.state.idempotency_store, RedisIdempotencyStore)


@pytest.mark.asyncio
async def test_api_lifespan_memory_idempotency_when_redis_unset():
    from mymlfw.api.app import create_app
    from mymlfw.api.idempotency import InMemoryIdempotencyStore
    from mymlfw.api.settings import Settings

    app = create_app(Settings(env="dev", mongo_uri="", redis_url=""))
    async with app.router.lifespan_context(app):
        assert app.state.redis is None
        assert isinstance(app.state.idempotency_store, InMemoryIdempotencyStore)
