"""Project roadmap strategies — service façade over ``saas.db.project_data``."""

from __future__ import annotations

import os
from typing import Any

from mymlfw.saas.brain_store import BRAIN_STORE, CampaignBrainStore
from mymlfw.saas.db import project_data
from mymlfw.saas.schemas import (
    RoadmapStrategyCreate,
    RoadmapStrategyResponse,
    RoadmapStrategyUpdate,
)


def _db_from_client(mongo_client: Any | None) -> Any | None:
    if mongo_client is None:
        return None
    from mymlfw.saas.db.client import get_saas_database

    return get_saas_database(
        mongo_client, os.environ.get("MYMLFW_MONGO_DB", "mymlfw")
    )


async def list_strategies(
    *,
    workspace_id: str,
    project_id: str,
    mongo_client: Any | None = None,
    brain: CampaignBrainStore | None = None,
) -> list[RoadmapStrategyResponse]:
    db = _db_from_client(mongo_client)
    if db is None:
        store = brain or BRAIN_STORE
        return store.list_roadmap_strategies(workspace_id, project_id)
    return await project_data.list_roadmap_strategies(db, workspace_id, project_id)


async def add_strategy(
    *,
    workspace_id: str,
    project_id: str,
    body: RoadmapStrategyCreate,
    mongo_client: Any | None = None,
    brain: CampaignBrainStore | None = None,
) -> RoadmapStrategyResponse:
    db = _db_from_client(mongo_client)
    if db is None:
        store = brain or BRAIN_STORE
        return store.add_roadmap_strategy(workspace_id, project_id, body)
    return await project_data.add_roadmap_strategy(
        db, workspace_id=workspace_id, project_id=project_id, body=body
    )


async def update_strategy(
    *,
    workspace_id: str,
    project_id: str,
    strategy_id: str,
    body: RoadmapStrategyUpdate,
    mongo_client: Any | None = None,
    brain: CampaignBrainStore | None = None,
) -> RoadmapStrategyResponse:
    db = _db_from_client(mongo_client)
    if db is None:
        store = brain or BRAIN_STORE
        return store.update_roadmap_strategy(
            workspace_id, project_id, strategy_id, body
        )
    return await project_data.update_roadmap_strategy(
        db,
        workspace_id=workspace_id,
        project_id=project_id,
        strategy_id=strategy_id,
        body=body,
    )
