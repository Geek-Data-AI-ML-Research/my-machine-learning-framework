"""Minimal FastAPI app: auth, me, persona switcher, health, OTel, middleware."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from mymlfw import __version__ as PKG_VERSION
from mymlfw.api.auth import AUTH_STORE, seed_dev_personas
from mymlfw.api.deps import get_current_principal
from mymlfw.api.idempotency import IdempotencyMiddleware
from mymlfw.api.middleware import ClientVersionMiddleware
from mymlfw.api.otel import setup_otel
from mymlfw.api.public_route import public_route
from mymlfw.api.routes_brain import router as brain_router
from mymlfw.api.routes_cloud import router as cloud_router
from mymlfw.api.routes_phase_c import router as phase_c_router
from mymlfw.api.routes_phase_c import sse_hello
from mymlfw.api.routes_phase_d import router as phase_d_router
from mymlfw.api.settings import Settings, get_settings
from mymlfw.saas.schemas import (
    HealthResponse,
    LoginRequest,
    MeResponse,
    McpGapReportCreate,
    McpGapReportListResponse,
    McpGapReportResponse,
    OrgFeatureFlagsUpdate,
    PatCreateRequest,
    PatCreateResponse,
    PatListItem,
    PersonaSwitchRequest,
    RegisterRequest,
    TokenResponse,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_otel("mymlfw-api")
        app.state.settings = settings
        app.state.mongo_client = None
        app.state.mongo_db = None
        app.state.redis = None
        app.state.redis_sync = None
        app.state.idempotency_store = None
        if settings.mongo_uri:
            try:
                from mymlfw.saas.db.client import create_saas_mongo_client, get_saas_database
                from mymlfw.saas.db import auth_data
                from mymlfw.saas.db.indexes import ensure_saas_indexes
                from mymlfw.saas.db.migrations import run_migrations

                client = create_saas_mongo_client(settings.mongo_uri)
                db = get_saas_database(client, settings.mongo_db)
                await run_migrations(db)
                await ensure_saas_indexes(db)
                app.state.mongo_client = client
                app.state.mongo_db = db
                # Stable Mongo personas — never seed in-memory AUTH_STORE when Mongo is up.
                if settings.env == "dev":
                    from mymlfw.saas.db import project_data

                    for persona, email in (
                        ("owner", "owner@localhost"),
                        ("member", "member@localhost"),
                        ("viewer", "viewer@localhost"),
                    ):
                        await auth_data.ensure_dev_persona(
                            db, persona=persona, email=email, password="devpassword"
                        )
                    # Re-attach orphaned Kaggle projects created under ephemeral
                    # in-memory orgs before auth was Mongo-backed.
                    owner = await auth_data.get_user_by_email(db, "owner@localhost")
                    if owner and owner.get("org_id"):
                        await project_data.claim_latest_kaggle_slug_for_org(
                            db, workspace_id=owner["org_id"], slug="vqcc"
                        )
            except Exception as exc:  # pragma: no cover - optional in unit tests
                app.state.mongo_error = str(exc)
                # Surface bind failures in container logs (silent None otherwise).
                import logging

                logging.getLogger("mymlfw.api").exception(
                    "mongo_bind_failed: %s", exc
                )
        else:
            # Pytest / local no-Mongo only.
            seed_dev_personas()
        if settings.redis_url:
            try:
                from mymlfw.api.idempotency import RedisIdempotencyStore
                from mymlfw.saas.redis_control import bind_redis, connect_redis

                redis_client, redis_sync = await connect_redis(settings.redis_url)
                bind_redis(redis_client, redis_sync)
                app.state.redis = redis_client
                app.state.redis_sync = redis_sync
                app.state.idempotency_store = RedisIdempotencyStore(redis_client)
            except Exception as exc:  # pragma: no cover - optional in unit tests
                app.state.redis_error = str(exc)
                from mymlfw.api.idempotency import InMemoryIdempotencyStore
                from mymlfw.saas.redis_control import bind_redis

                bind_redis(None, None)
                app.state.idempotency_store = InMemoryIdempotencyStore()
        else:
            from mymlfw.api.idempotency import InMemoryIdempotencyStore
            from mymlfw.saas.redis_control import bind_redis

            bind_redis(None, None)
            app.state.idempotency_store = InMemoryIdempotencyStore()
        yield
        from mymlfw.saas.redis_control import close_redis

        await close_redis(
            getattr(app.state, "redis", None),
            getattr(app.state, "redis_sync", None),
        )
        client = getattr(app.state, "mongo_client", None)
        if client is not None:
            await client.close()

    app = FastAPI(
        title="mymlfw Campaign SaaS API",
        version=settings.api_version or PKG_VERSION,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ClientVersionMiddleware, server_version=settings.api_version)
    app.add_middleware(IdempotencyMiddleware)
    app.include_router(brain_router)
    app.include_router(phase_c_router)
    app.include_router(cloud_router)
    app.include_router(phase_d_router)

    @app.get("/health", response_model=HealthResponse)
    @public_route
    async def health() -> HealthResponse:
        return HealthResponse(version=settings.api_version)

    @app.post("/v1/auth/register", response_model=TokenResponse)
    @public_route
    async def register(request: Request, body: RegisterRequest) -> TokenResponse:
        mongo = getattr(request.app.state, "mongo_db", None)
        try:
            if mongo is not None:
                from mymlfw.saas.db import auth_data

                return await auth_data.register_user(
                    mongo,
                    email=body.email,
                    password=body.password,
                    display_name=body.display_name,
                )
            return AUTH_STORE.register(body.email, body.password, body.display_name)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/auth/login", response_model=TokenResponse)
    @public_route
    async def login(request: Request, body: LoginRequest) -> TokenResponse:
        mongo = getattr(request.app.state, "mongo_db", None)
        try:
            if mongo is not None:
                from mymlfw.saas.db import auth_data

                return await auth_data.login_user(
                    mongo, email=body.email, password=body.password
                )
            return AUTH_STORE.login(body.email, body.password)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @app.get("/v1/auth/github/start")
    @public_route
    async def github_start() -> dict[str, Any]:
        if not settings.github_oauth_stub and not settings.github_client_id:
            raise HTTPException(status_code=503, detail="github_oauth_unconfigured")
        return {
            "authorize_url": "https://github.com/login/oauth/authorize",
            "client_id": settings.github_client_id,
            "stub": settings.github_oauth_stub,
        }

    @app.post("/v1/auth/github/callback", response_model=TokenResponse)
    @public_route
    async def github_callback(request: Request, code: str = "dev") -> TokenResponse:
        mongo = getattr(request.app.state, "mongo_db", None)
        if settings.github_oauth_stub:
            if mongo is not None:
                from mymlfw.saas.db import auth_data

                email = f"gh_{(code[:12] or 'dev')}@users.noreply.github.com"
                return await auth_data.github_register_or_login(
                    mongo,
                    email=email,
                    display_name="GitHub Dev",
                    password="gh-oauth-stub",
                )
            return AUTH_STORE.github_oauth_stub(code)
        if not settings.github_client_id or not settings.github_client_secret:
            raise HTTPException(status_code=503, detail="github_oauth_unconfigured")
        try:
            return AUTH_STORE.github_oauth_live(
                code=code,
                client_id=settings.github_client_id,
                client_secret=settings.github_client_secret,
            )
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    @app.patch("/v1/orgs/current/feature-flags")
    async def patch_org_feature_flags(
        request: Request,
        body: OrgFeatureFlagsUpdate,
        principal: dict[str, Any] = Depends(get_current_principal),
    ) -> dict[str, Any]:
        from mymlfw.api.deps import require_owner
        from mymlfw.saas.control_plane import set_org_policy
        from mymlfw.saas.schemas import FeatureFlags, OrgResponse

        org = principal.get("org")
        if org is None:
            raise HTTPException(status_code=404, detail="no_org")
        require_owner(principal, action="patch feature_flags")
        updates = body.model_dump(exclude_none=True)
        mongo = getattr(request.app.state, "mongo_db", None)
        if mongo is not None:
            from mymlfw.saas.db import auth_data

            updated = await auth_data.update_org_feature_flags(mongo, org.id, updates)
            flags = FeatureFlags(**(updated.get("feature_flags") or {}))
            set_org_policy(org.id, feature_flags=flags)
            from mymlfw.saas.schemas import OrgEntitlements

            ent = updated.get("entitlements") or {}
            return OrgResponse(
                id=updated["_id"],
                slug=updated["slug"],
                name=updated["name"],
                plan=str(updated.get("plan") or "dev"),
                entitlements=OrgEntitlements(**ent) if isinstance(ent, dict) else org.entitlements,
                feature_flags=flags,
            ).model_dump(mode="json")
        updated = AUTH_STORE.update_feature_flags(org.id, updates)
        flags = FeatureFlags(**(updated.get("feature_flags") or {}))
        set_org_policy(org.id, feature_flags=flags)
        return OrgResponse(**updated).model_dump(mode="json")

    @app.get("/v1/me", response_model=MeResponse)
    async def me(principal: dict[str, Any] = Depends(get_current_principal)) -> MeResponse:
        return MeResponse(
            user=principal["user"],
            org=principal["org"],
            persona=principal.get("persona"),
        )

    @app.get("/v1/orgs/current")
    async def current_org(
        principal: dict[str, Any] = Depends(get_current_principal),
    ) -> dict[str, Any]:
        org = principal.get("org")
        if org is None:
            raise HTTPException(status_code=404, detail="no_org")
        return org.model_dump()

    @app.get("/v1/orgs/current/pats", response_model=list[PatListItem])
    async def list_org_pats(
        request: Request,
        principal: dict[str, Any] = Depends(get_current_principal),
    ) -> list[PatListItem]:
        from mymlfw.api.deps import require_owner

        org = principal.get("org")
        if org is None:
            raise HTTPException(status_code=404, detail="no_org")
        require_owner(principal, action="list MCP PATs")
        mongo = getattr(request.app.state, "mongo_db", None)
        if mongo is None:
            raise HTTPException(status_code=503, detail="mongo_required")
        from mymlfw.saas.db import pat_data

        rows = await pat_data.list_pats(mongo, workspace_id=org.id)
        return [PatListItem(**row) for row in rows]

    @app.post("/v1/orgs/current/pats", response_model=PatCreateResponse)
    async def create_org_pat(
        request: Request,
        body: PatCreateRequest,
        principal: dict[str, Any] = Depends(get_current_principal),
    ) -> PatCreateResponse:
        from mymlfw.api.deps import require_owner

        org = principal.get("org")
        if org is None:
            raise HTTPException(status_code=404, detail="no_org")
        require_owner(principal, action="mint MCP PAT")
        mongo = getattr(request.app.state, "mongo_db", None)
        if mongo is None:
            raise HTTPException(status_code=503, detail="mongo_required")
        scopes = body.scopes or ["mcp:worker"]
        allowed = {"mcp:worker", "mcp:cloud", "mcp:admin"}
        if not set(scopes).issubset(allowed):
            raise HTTPException(status_code=400, detail="invalid_pat_scopes")
        from mymlfw.saas.db import pat_data

        try:
            return await pat_data.create_pat(
                mongo,
                workspace_id=org.id,
                project_id=body.project_id,
                scopes=list(scopes),
                label=body.label or "mcp-worker",
                replace=bool(body.replace),
            )
        except pat_data.PatExistsError as exc:
            prefixes = [str(r.get("token_prefix") or "") for r in exc.active]
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "pat_exists",
                    "message": (
                        "An active MCP PAT already exists for this workspace. "
                        "Pass replace=true after confirming with the user."
                    ),
                    "active_prefixes": prefixes,
                    "suggested_fix": "Confirm replace, then POST with replace=true",
                },
            ) from exc

    @app.delete("/v1/orgs/current/pats/{token_id}")
    async def revoke_org_pat(
        request: Request,
        token_id: str,
        principal: dict[str, Any] = Depends(get_current_principal),
    ) -> dict[str, Any]:
        from mymlfw.api.deps import require_owner

        org = principal.get("org")
        if org is None:
            raise HTTPException(status_code=404, detail="no_org")
        require_owner(principal, action="revoke MCP PAT")
        mongo = getattr(request.app.state, "mongo_db", None)
        if mongo is None:
            raise HTTPException(status_code=503, detail="mongo_required")
        from mymlfw.saas.db import pat_data

        ok = await pat_data.revoke_pat(
            mongo, workspace_id=org.id, token_id=token_id
        )
        if not ok:
            raise HTTPException(status_code=404, detail="pat_not_found")
        return {"revoked": True, "token_id": token_id}

    @app.get("/v1/orgs/current/mcp-gaps", response_model=McpGapReportListResponse)
    async def list_mcp_gaps(
        request: Request,
        principal: dict[str, Any] = Depends(get_current_principal),
        project_id: str | None = None,
    ) -> McpGapReportListResponse:
        org = principal.get("org")
        if org is None:
            raise HTTPException(status_code=404, detail="no_org")
        mongo = getattr(request.app.state, "mongo_db", None)
        from mymlfw.saas.db import mcp_gap_data

        gaps = await mcp_gap_data.list_gaps(
            mongo, workspace_id=org.id, project_id=project_id
        )
        return McpGapReportListResponse(gaps=gaps)

    @app.post("/v1/orgs/current/mcp-gaps", response_model=McpGapReportResponse)
    async def create_mcp_gap(
        request: Request,
        body: McpGapReportCreate,
        principal: dict[str, Any] = Depends(get_current_principal),
    ) -> McpGapReportResponse:
        org = principal.get("org")
        if org is None:
            raise HTTPException(status_code=404, detail="no_org")
        mongo = getattr(request.app.state, "mongo_db", None)
        from mymlfw.saas.db import mcp_gap_data

        return await mcp_gap_data.create_gap(
            mongo, workspace_id=org.id, body=body
        )

    @app.post("/v1/dev/persona", response_model=MeResponse)
    async def switch_persona(
        request: Request,
        body: PersonaSwitchRequest,
        principal: dict[str, Any] = Depends(get_current_principal),
    ) -> MeResponse:
        if settings.env != "dev":
            raise HTTPException(status_code=404, detail="not_found")
        mongo = getattr(request.app.state, "mongo_db", None)
        if mongo is not None:
            from mymlfw.saas.db import auth_data

            await auth_data.set_user_persona(
                mongo, principal["user"].id, body.persona
            )
            auth_header = request.headers.get("authorization") or ""
            token = (
                auth_header.split(" ", 1)[1].strip()
                if auth_header.lower().startswith("bearer ")
                else ""
            )
            refreshed = (
                await auth_data.resolve_session(mongo, token) if token else None
            )
        else:
            AUTH_STORE.set_persona(principal["user"].id, body.persona)
            token = next(
                (
                    tok
                    for tok, uid in AUTH_STORE.sessions.items()
                    if uid == principal["user"].id
                ),
                None,
            )
            if token is None:
                raise HTTPException(status_code=401, detail="invalid_token")
            refreshed = AUTH_STORE.resolve(token)
        if refreshed is None:
            raise HTTPException(status_code=401, detail="invalid_token")
        return MeResponse(
            user=refreshed["user"],
            org=refreshed["org"],
            persona=refreshed.get("persona"),
        )

    @app.get("/v1/events")
    async def events_stub(
        request: Request,
        principal: dict[str, Any] = Depends(get_current_principal),
    ) -> StreamingResponse:
        """SSE shell. Auth via Authorization header (never ?token=). Resume via Last-Event-ID.

        When Redis is up, also subscribe for multi-worker fan-out (train_strip etc.).
        """
        _ = principal
        origin = request.headers.get("origin")
        allowed = {o.strip() for o in (settings.cors_origins or "").split(",") if o.strip()}
        if origin and origin not in allowed:
            raise HTTPException(status_code=403, detail="origin_rejected")
        last = request.headers.get("last-event-id")
        start = int(last) + 1 if last and last.isdigit() else 0
        redis_up = getattr(request.app.state, "redis", None) is not None

        async def gen():
            yield ": ping\n\n"
            chunks = sse_hello()
            for chunk in chunks:
                if chunk.startswith("id: "):
                    eid = chunk.split("\n", 1)[0].removeprefix("id: ").strip()
                    if eid.isdigit() and int(eid) < start:
                        continue
                yield chunk
            if not redis_up:
                return
            from mymlfw.saas.redis_control import iter_sse_from_redis, publish_sse_event

            strip = {"fold": "3/5", "val_metric": None, "gpu": None}
            # Fan-out to other API workers; also emit locally for one-shot poll clients.
            await publish_sse_event(
                event="train_strip", data=strip, event_id=1
            )
            if start <= 1:
                import json as _json

                yield (
                    "id: 1\nevent: train_strip\ndata: "
                    + _json.dumps(strip)
                    + "\n\n"
                )
            # Brief subscribe drain (multi-worker messages already in flight).
            async for chunk in iter_sse_from_redis(stop_after_s=0.25):
                if chunk.startswith("id: "):
                    eid = chunk.split("\n", 1)[0].removeprefix("id: ").strip()
                    if eid.isdigit() and int(eid) < start:
                        continue
                yield chunk

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    return app


app = create_app()


def main() -> None:
    import os

    import uvicorn

    settings = get_settings()
    # Bind loopback by default (AGENTS: do not publish control plane on 0.0.0.0).
    # Opt into all-interfaces only with MYMLFW_API_BIND=0.0.0.0 behind a reverse proxy.
    host = os.environ.get("MYMLFW_API_BIND", "127.0.0.1").strip() or "127.0.0.1"
    uvicorn.run(
        "mymlfw.api.app:app",
        host=host,
        port=8000,
        reload=settings.env == "dev",
    )


if __name__ == "__main__":
    main()
