"""Process runtime helpers shared by API / MCP (Mongo optional)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from mymlfw.saas.brain_store import BRAIN_STORE, CampaignBrainStore
from mymlfw.saas.db.project_db import ProjectScopedDB
from mymlfw.saas.missions import MissionService
from mymlfw.saas.pats import PAT_STORE, PatStore
from mymlfw.saas.providers.service import InMemoryCloudStore


@dataclass
class ControlPlaneRuntime:
    missions: MissionService
    pats: PatStore
    mongo_client: Any | None = None
    brain: CampaignBrainStore = BRAIN_STORE
    cloud_store: InMemoryCloudStore | None = None


async def open_control_plane_runtime(
    *,
    brain: CampaignBrainStore | None = None,
    pats: PatStore | None = None,
    missions: MissionService | None = None,
    mongo_uri: str | None = None,
    mongo_db_name: str | None = None,
) -> ControlPlaneRuntime:
    """Build MissionService (+ optional Mongo ProjectScopedDB factory)."""
    brain = brain or BRAIN_STORE
    injected_pats = pats is not None
    mongo_client = None
    factory: Callable[[str, str], ProjectScopedDB] | None = None

    uri = (mongo_uri if mongo_uri is not None else os.environ.get("MYMLFW_MONGO_URI", "")).strip()
    db_name = mongo_db_name or os.environ.get("MYMLFW_MONGO_DB", "mymlfw")
    mongo_db = None

    if missions is None and uri:
        try:
            from mymlfw.saas.db.client import create_saas_mongo_client, get_saas_database

            client = create_saas_mongo_client(uri, appname="mymlfw-control")
            db = get_saas_database(client, db_name)
            mongo_db = db

            def _project_db(workspace_id: str, project_id: str) -> ProjectScopedDB:
                return ProjectScopedDB(
                    db, workspace_id=workspace_id, project_id=project_id
                )

            factory = _project_db
            mongo_client = client
        except Exception:
            factory = None
            mongo_db = None
            if mongo_client is not None:
                await mongo_client.close()
            mongo_client = None

    if missions is None:
        missions = MissionService(
            brain=brain, project_db_factory=factory, mongo_db=mongo_db
        )

    if not injected_pats:
        pats = PatStore(mongo_db=mongo_db) if mongo_db is not None else PAT_STORE
    assert pats is not None

    from mymlfw.saas.control_plane import get_shared_cloud_store

    return ControlPlaneRuntime(
        missions=missions,
        pats=pats,
        mongo_client=mongo_client,
        brain=brain,
        cloud_store=get_shared_cloud_store(),
    )


async def close_control_plane_runtime(runtime: ControlPlaneRuntime) -> None:
    if runtime.mongo_client is not None:
        await runtime.mongo_client.close()
