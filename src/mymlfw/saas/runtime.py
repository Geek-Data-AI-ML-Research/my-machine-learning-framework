"""Process runtime helpers shared by API / MCP (Mongo optional)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from mymlfw.saas.brain_store import BRAIN_STORE, CampaignBrainStore
from mymlfw.saas.db.project_db import ProjectScopedDB
from mymlfw.saas.missions import MissionService
from mymlfw.saas.pats import PAT_STORE, PatStore


@dataclass
class ControlPlaneRuntime:
    missions: MissionService
    pats: PatStore
    mongo_client: Any | None = None
    brain: CampaignBrainStore = BRAIN_STORE


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
    pats = pats or PAT_STORE
    mongo_client = None
    factory: Callable[[str, str], ProjectScopedDB] | None = None

    uri = (mongo_uri if mongo_uri is not None else os.environ.get("MYMLFW_MONGO_URI", "")).strip()
    db_name = mongo_db_name or os.environ.get("MYMLFW_MONGO_DB", "mymlfw")

    if missions is None and uri:
        try:
            from mymlfw.saas.db.client import create_saas_mongo_client, get_saas_database

            client = create_saas_mongo_client(uri, appname="mymlfw-control")
            db = get_saas_database(client, db_name)

            def _project_db(workspace_id: str, project_id: str) -> ProjectScopedDB:
                return ProjectScopedDB(
                    db, workspace_id=workspace_id, project_id=project_id
                )

            factory = _project_db
            mongo_client = client
        except Exception:
            factory = None
            if mongo_client is not None:
                await mongo_client.close()
            mongo_client = None

    if missions is None:
        missions = MissionService(brain=brain, project_db_factory=factory)

    workspace = os.environ.get("MYMLFW_MCP_WORKSPACE_ID", "").strip()
    if workspace:
        brain.ensure_demo_campaign(
            org_id=workspace, org_slug=f"org-{workspace[-6:].lower()}"
        )

    return ControlPlaneRuntime(
        missions=missions,
        pats=pats,
        mongo_client=mongo_client,
        brain=brain,
    )


async def close_control_plane_runtime(runtime: ControlPlaneRuntime) -> None:
    if runtime.mongo_client is not None:
        await runtime.mongo_client.close()
