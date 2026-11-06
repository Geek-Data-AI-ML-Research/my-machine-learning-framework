"""Wave 1 unit tests: ScopedCollection, indexes, codecs, idempotency."""

from __future__ import annotations

from datetime import UTC

import pytest

pymongo = pytest.importorskip("pymongo")
fastapi = pytest.importorskip("fastapi")


def test_codec_options_tz_aware_utc():
    from mymlfw.saas.db.client import (
        client_codec_is_tz_aware,
        create_saas_mongo_client,
        pack_embedding_f32,
    )

    client = create_saas_mongo_client("mongodb://127.0.0.1:27017")
    assert client_codec_is_tz_aware(client)
    assert client.codec_options.tz_aware is True
    assert client.codec_options.tzinfo is UTC
    vec = pack_embedding_f32([0.1, -0.2, 0.3])
    assert vec is not None
    with pytest.raises(ValueError):
        pack_embedding_f32([float("nan")])


def test_scoped_collection_overwrites_tenant_keys():
    from mymlfw.saas.db.tenant_repo import ScopedCollection, TenantFilterError

    class _Dummy:
        name = "experiments"

    scoped = ScopedCollection(
        _Dummy(), workspace_id="org_01HTESTWORKSPACE0000000000", project_id="prj_01HTESTPROJECT000000000000"
    )
    filt = scoped.preview_filter(
        {
            "workspace_id": "org_OTHER",
            "project_id": "prj_OTHER",
            "status": "open",
        }
    )
    assert filt["workspace_id"] == "org_01HTESTWORKSPACE0000000000"
    assert filt["project_id"] == "prj_01HTESTPROJECT000000000000"
    assert filt["deleted_at"] is None
    assert filt["status"] == "open"

    stamped = scoped.preview_document(
        {"_id": "exp_1", "workspace_id": "org_TAMPER", "variable": "lora_r"}
    )
    assert stamped["workspace_id"] == "org_01HTESTWORKSPACE0000000000"
    assert stamped["project_id"] == "prj_01HTESTPROJECT000000000000"

    updated = scoped.preview_update(
        {"$set": {"workspace_id": "org_TAMPER", "cv_mean": 0.1, "_id": "nope"}}
    )
    assert "workspace_id" not in updated["$set"]
    assert "_id" not in updated["$set"]
    assert updated["$set"]["cv_mean"] == 0.1

    with pytest.raises(TenantFilterError):
        scoped.preview_filter({"$where": "1"})


def test_one_open_lever_index_definition_present():
    from mymlfw.saas.db.indexes import ONE_OPEN_LEVER_INDEX, OUTBOX_PARTIAL_INDEX

    assert ONE_OPEN_LEVER_INDEX["unique"] is True
    assert ONE_OPEN_LEVER_INDEX["name"] == "uniq_one_open_lever"
    assert ONE_OPEN_LEVER_INDEX["partialFilterExpression"] == {
        "status": "open",
        "deleted_at": None,
    }
    assert OUTBOX_PARTIAL_INDEX["partialFilterExpression"]["status"]["$in"] == [
        "pending",
        "processing",
    ]


@pytest.mark.asyncio
async def test_idempotency_in_progress_no_cache_5xx():
    from httpx import ASGITransport, AsyncClient

    from mymlfw.api.idempotency import (
        IDEMPOTENCY_HEADER,
        IdempotencyMiddleware,
        InMemoryIdempotencyStore,
    )
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse, PlainTextResponse
    from starlette.routing import Route

    store = InMemoryIdempotencyStore()

    hits = {"n": 0}

    async def slow_ok(request):
        hits["n"] += 1
        if request.headers.get("x-force-500") == "1":
            return PlainTextResponse("fail", status_code=500)
        return JSONResponse({"ok": True, "n": hits["n"]})

    inner = Starlette(routes=[Route("/v1/probe", slow_ok, methods=["POST"])])
    wrapped = IdempotencyMiddleware(inner, store=store)

    transport = ASGITransport(app=wrapped)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First request marks IN_PROGRESS then completes.
        r1 = await client.post(
            "/v1/probe", headers={IDEMPOTENCY_HEADER: "k1"}
        )
        assert r1.status_code == 200
        assert r1.json()["n"] == 1

        # Replay returns cached body without re-executing.
        r2 = await client.post(
            "/v1/probe", headers={IDEMPOTENCY_HEADER: "k1"}
        )
        assert r2.status_code == 200
        assert r2.headers.get("x-idempotency-replayed") == "true"
        assert r2.json()["n"] == 1
        assert hits["n"] == 1

        # Simulate IN_PROGRESS collision.
        store._entries["POST:/v1/probe:k2"] = {"status": "IN_PROGRESS"}
        r3 = await client.post(
            "/v1/probe", headers={IDEMPOTENCY_HEADER: "k2"}
        )
        assert r3.status_code == 409
        assert r3.json()["error_code"] == "idempotency_in_progress"
        assert r3.headers.get("cache-control") == "no-store"

        # 5xx must not be cached.
        r4 = await client.post(
            "/v1/probe",
            headers={IDEMPOTENCY_HEADER: "k3", "x-force-500": "1"},
        )
        assert r4.status_code == 500
        assert await store.get("POST:/v1/probe:k3") is None


def test_metric_forbids_nan():
    pydantic = pytest.importorskip("pydantic")
    from mymlfw.saas.schemas import MetricSample

    with pytest.raises(pydantic.ValidationError):
        MetricSample(name="cv", value=float("nan"))
    with pytest.raises(pydantic.ValidationError):
        MetricSample(name="cv", value=float("inf"))
    assert MetricSample(name="cv", value=0.5).value == 0.5


def test_public_route_marker():
    from mymlfw.api.public_route import is_public_route, public_route

    @public_route
    def health():
        return "ok"

    assert is_public_route(health) is True
    assert is_public_route(lambda: None) is False
