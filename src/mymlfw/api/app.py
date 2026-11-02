"""Minimal FastAPI app: auth, me, persona switcher, health, OTel, middleware."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
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
from mymlfw.api.settings import Settings, get_settings
from mymlfw.saas.schemas import (
    HealthResponse,
    LoginRequest,
    MeResponse,
    PersonaSwitchRequest,
    RegisterRequest,
    TokenResponse,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_otel("mymlfw-api")
        seed_dev_personas()
        app.state.settings = settings
        app.state.mongo_client = None
        app.state.mongo_db = None
        if settings.mongo_uri:
            try:
                from mymlfw.saas.db.client import create_saas_mongo_client, get_saas_database
                from mymlfw.saas.db.indexes import ensure_saas_indexes
                from mymlfw.saas.db.migrations import run_migrations

                client = create_saas_mongo_client(settings.mongo_uri)
                db = get_saas_database(client, settings.mongo_db)
                await run_migrations(db)
                await ensure_saas_indexes(db)
                app.state.mongo_client = client
                app.state.mongo_db = db
            except Exception as exc:  # pragma: no cover - optional in unit tests
                app.state.mongo_error = str(exc)
        yield
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

    @app.get("/health", response_model=HealthResponse)
    @public_route
    async def health() -> HealthResponse:
        return HealthResponse(version=settings.api_version)

    @app.post("/v1/auth/register", response_model=TokenResponse)
    @public_route
    async def register(body: RegisterRequest) -> TokenResponse:
        try:
            return AUTH_STORE.register(body.email, body.password, body.display_name)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/auth/login", response_model=TokenResponse)
    @public_route
    async def login(body: LoginRequest) -> TokenResponse:
        try:
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
            "client_id": settings.github_client_id or "stub",
            "stub": settings.github_oauth_stub,
        }

    @app.post("/v1/auth/github/callback", response_model=TokenResponse)
    @public_route
    async def github_callback(code: str = "dev") -> TokenResponse:
        return AUTH_STORE.github_oauth_stub(code)

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

    @app.post("/v1/dev/persona", response_model=MeResponse)
    async def switch_persona(
        body: PersonaSwitchRequest,
        principal: dict[str, Any] = Depends(get_current_principal),
    ) -> MeResponse:
        if settings.env != "dev":
            raise HTTPException(status_code=404, detail="not_found")
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
        assert refreshed is not None
        return MeResponse(
            user=refreshed["user"],
            org=refreshed["org"],
            persona=refreshed.get("persona"),
        )

    @app.get("/v1/events")
    async def events_stub(
        principal: dict[str, Any] = Depends(get_current_principal),
    ) -> StreamingResponse:
        """SSE shell — Last-Event-ID multiplexing lands with live strips."""
        _ = principal

        async def gen():
            yield "id: 0\nevent: hello\ndata: {\"ok\":true}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "mymlfw.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.env == "dev",
    )


if __name__ == "__main__":
    main()
