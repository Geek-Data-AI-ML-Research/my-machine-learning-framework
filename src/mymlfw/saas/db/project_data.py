"""Workspace/project CRUD for Campaign brain data via Mongo.

Routes and MCP must call these helpers (or ``ProjectScopedDB``) — never touch
raw ``AsyncDatabase`` collections outside this package.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from mymlfw.saas.brain_store import CampaignBrainStore
from mymlfw.saas.dashboard import compute_dashboard, experiments_facet_pipeline
from mymlfw.saas.db.project_db import ProjectScopedDB
from mymlfw.saas.ids import new_project_id, new_snapshot_id
from mymlfw.saas.schemas import (
    DashboardResponse,
    ProjectKind,
    ProjectSummary,
    PublicSnapshotResponse,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def project_summary_from_doc(proj: dict[str, Any]) -> ProjectSummary:
    from mymlfw.saas.schemas import FoldMeta

    return ProjectSummary(
        id=proj["_id"],
        slug=proj["slug"],
        name=proj["name"],
        kind=ProjectKind(proj["kind"]),
        is_demo=bool(proj.get("is_demo")),
        folds=FoldMeta(
            folds_sha256=proj.get("folds_sha256"),
            adv_auc=proj.get("adv_auc"),
            epoch_id=proj.get("epoch_id"),
            n_folds=proj.get("n_folds"),
            artifact_key=proj.get("folds_artifact_key"),
        ),
        public_share_slug=proj.get("public_share_slug"),
        updated_at=proj.get("updated_at"),
    )


async def get_project(
    db: AsyncDatabase, workspace_id: str, project_id: str
) -> dict[str, Any] | None:
    doc = await db["projects"].find_one(
        {
            "_id": project_id,
            "workspace_id": workspace_id,
            "deleted_at": None,
        }
    )
    return doc


async def list_projects(
    db: AsyncDatabase, workspace_id: str
) -> list[ProjectSummary]:
    cursor = db["projects"].find(
        {"workspace_id": workspace_id, "deleted_at": None}
    ).sort("updated_at", -1)
    return [project_summary_from_doc(doc) async for doc in cursor]


_SCOPED_COLLECTIONS = (
    "project_goals",
    "experiments",
    "missions",
    "dead_ends",
    "project_sources",
    "project_roadmap_strategies",
    "daily_progress",
    "project_credits",
    "outbox_events",
    "autopilot_sessions",
    "autopilot_nodes",
)


async def rehome_project(
    db: AsyncDatabase,
    *,
    project_id: str,
    to_workspace_id: str,
) -> dict[str, Any] | None:
    """Move a project (+ scoped child docs) to ``to_workspace_id``.

    Used when in-memory auth previously orphaned Mongo projects under ephemeral orgs.
    """
    now = _utcnow()
    proj = await db["projects"].find_one({"_id": project_id, "deleted_at": None})
    if proj is None:
        return None
    old = proj.get("workspace_id")
    if old == to_workspace_id:
        return proj
    await db["projects"].update_one(
        {"_id": project_id},
        {"$set": {"workspace_id": to_workspace_id, "updated_at": now}},
    )
    if old:
        for coll in _SCOPED_COLLECTIONS:
            await db[coll].update_many(
                {"workspace_id": old, "project_id": project_id},
                {"$set": {"workspace_id": to_workspace_id}},
            )
    return await db["projects"].find_one({"_id": project_id})


async def soft_delete_project(
    db: AsyncDatabase, *, project_id: str, workspace_id: str | None = None
) -> bool:
    filt: dict[str, Any] = {"_id": project_id, "deleted_at": None}
    if workspace_id:
        filt["workspace_id"] = workspace_id
    res = await db["projects"].update_one(
        filt, {"$set": {"deleted_at": _utcnow(), "updated_at": _utcnow()}}
    )
    return bool(res.modified_count)


async def claim_latest_kaggle_slug_for_org(
    db: AsyncDatabase,
    *,
    workspace_id: str,
    slug: str = "vqcc",
) -> dict[str, Any] | None:
    """Keep the newest live project with ``slug``; soft-delete sibling orphans; rehome."""
    cursor = db["projects"].find(
        {"slug": slug, "deleted_at": None, "kind": "kaggle"}
    ).sort("_id", -1)
    rows = [doc async for doc in cursor]
    if not rows:
        return None
    keeper = rows[0]
    for dup in rows[1:]:
        await soft_delete_project(db, project_id=dup["_id"])
    return await rehome_project(
        db, project_id=keeper["_id"], to_workspace_id=workspace_id
    )


async def ensure_org_project(
    db: AsyncDatabase,
    workspace_id: str,
    project_id: str,
    *,
    name: str | None = None,
) -> dict[str, Any] | None:
    """Upsert a project under ``workspace_id``. None if owned by another org."""
    existing = await db["projects"].find_one({"_id": project_id})
    if existing is not None:
        if existing.get("workspace_id") != workspace_id:
            return None
        if existing.get("deleted_at") is not None:
            return None
        return existing
    if not str(project_id).startswith("prj_"):
        return None
    now = _utcnow()
    project = {
        "_id": project_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "schema_version": 1,
        "slug": (name or project_id)[:48].lower().replace(" ", "-"),
        "name": name or project_id,
        "kind": ProjectKind.standalone.value,
        "is_demo": False,
        "epoch_id": "epoch_0",
        "folds_sha256": secrets.token_hex(32),
        "adv_auc": None,
        "n_folds": 5,
        "folds_artifact_key": f"projects/{project_id}/folds.parquet",
        "public_share_slug": None,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
    await db["projects"].insert_one(project)
    return project


async def _persist_brain_bundle(
    db: AsyncDatabase, store: CampaignBrainStore, project_id: str
) -> None:
    proj = store.projects[project_id]
    await db["projects"].replace_one(
        {"_id": project_id}, proj, upsert=True
    )
    for goal in store.goals.get(project_id, []):
        await db["project_goals"].replace_one(
            {"_id": goal["_id"]}, goal, upsert=True
        )
    for exp in store.experiments.get(project_id, []):
        await db["experiments"].replace_one(
            {"_id": exp["_id"]}, exp, upsert=True
        )
    for mission in store.missions.get(project_id, []):
        await db["missions"].replace_one(
            {"_id": mission["_id"]}, mission, upsert=True
        )
    for dead in store.dead_ends.get(project_id, []):
        await db["dead_ends"].replace_one(
            {"_id": dead["_id"]}, dead, upsert=True
        )
    for card in store.episode_cards.get(project_id, []):
        await db["memory_chunks"].replace_one(
            {"_id": card["_id"]}, card, upsert=True
        )
    for axiom in store.axioms.get(project_id, []):
        await db["project_axioms"].replace_one(
            {"_id": axiom["_id"]}, axiom, upsert=True
        )


async def ensure_demo_campaign(
    db: AsyncDatabase, *, workspace_id: str, org_slug: str
) -> ProjectSummary:
    """Idempotent Demo Campaign seed into Mongo (same shape as BRAIN_STORE)."""
    existing = await db["projects"].find_one(
        {
            "workspace_id": workspace_id,
            "is_demo": True,
            "deleted_at": None,
        }
    )
    if existing is not None:
        return project_summary_from_doc(existing)

    # Build docs via the in-memory seeder, then persist (no production reads
    # from the global BRAIN_STORE).
    tmp = CampaignBrainStore()
    summary = tmp.ensure_demo_campaign(org_id=workspace_id, org_slug=org_slug)
    await _persist_brain_bundle(db, tmp, summary.id)
    return summary


async def load_dashboard(
    db: AsyncDatabase, workspace_id: str, project_id: str
) -> DashboardResponse | None:
    proj = await get_project(db, workspace_id, project_id)
    if proj is None:
        return None
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    try:
        cursor = await pdb.experiments.aggregate(experiments_facet_pipeline())
        _ = [doc async for doc in cursor]
    except Exception:
        pass
    goals = await pdb.list_goal_docs()
    experiments = await pdb.list_experiment_docs()
    missions = await pdb.list_mission_docs()
    dead_ends = await pdb.list_dead_end_docs()
    kaggle_panel = None
    intel = proj.get("kaggle_intel") if isinstance(proj.get("kaggle_intel"), dict) else None
    if intel or proj.get("kind") == ProjectKind.kaggle.value:
        from mymlfw.saas.db.kaggle_docs import finite_float, finite_int, parse_utc
        from mymlfw.saas.schemas import DashboardKagglePanel

        kaggle_panel = DashboardKagglePanel(
            linked=bool(proj.get("kaggle_competition")),
            rank=finite_int((intel or {}).get("rank")),
            public_score=finite_float((intel or {}).get("public_score")),
            medal_pace=(intel or {}).get("medal_pace"),
            last_sync=parse_utc((intel or {}).get("last_sync")),
        )
    return compute_dashboard(
        project_id=project_id,
        goals=goals,
        experiments=experiments,
        missions=missions,
        dead_ends=dead_ends,
        folds_sha256=proj.get("folds_sha256"),
        adv_auc=proj.get("adv_auc"),
        kaggle=kaggle_panel,
    )


async def store_project_kaggle_token(
    db: AsyncDatabase,
    *,
    workspace_id: str,
    project_id: str,
    blob: dict[str, Any],
) -> None:
    """Persist envelope blob on the project (ciphertext stays server-side binData)."""
    from mymlfw.saas.db.kaggle_docs import envelope_blob_for_mongo

    now = _utcnow()
    sealed = envelope_blob_for_mongo(blob)
    await db["projects"].update_one(
        {"_id": project_id, "workspace_id": workspace_id, "deleted_at": None},
        {
            "$set": {
                "kaggle_token_blob": sealed,
                "updated_at": now,
            }
        },
    )


async def store_project_kaggle_intel(
    db: AsyncDatabase,
    *,
    workspace_id: str,
    project_id: str,
    panel: dict[str, Any],
) -> dict[str, Any]:
    """Persist BSON-normalized intel; returns the stored document."""
    from mymlfw.saas.db.kaggle_docs import intel_doc_for_mongo

    now = _utcnow()
    doc = intel_doc_for_mongo(panel)
    await db["projects"].update_one(
        {"_id": project_id, "workspace_id": workspace_id, "deleted_at": None},
        {"$set": {"kaggle_intel": doc, "updated_at": now}},
    )
    return doc


async def store_project_kaggle_data(
    db: AsyncDatabase,
    *,
    workspace_id: str,
    project_id: str,
    inventory: dict[str, Any],
    credit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist inventory (+ credit upsert) in one transaction; enqueue license outbox."""
    from mymlfw.saas.db.kaggle_docs import credit_doc_for_mongo, inventory_doc_for_mongo
    from mymlfw.saas.db.outbox import enqueue_outbox_event

    now = _utcnow()
    inv_doc = inventory_doc_for_mongo(inventory)
    credit_doc = credit_doc_for_mongo(credit, now=now) if credit is not None else None
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    client = db.client

    async def _txn(session: Any) -> dict[str, Any]:
        # Explicit session= only — avoid session.bind() inside with_transaction
        # (w=majority + bind → writeConcern not allowed in multi-statement txn).
        if credit_doc is not None:
            existing = await pdb.project_credits.find_one(
                {"identifier_key": credit_doc["identifier_key"]},
                session=session,
            )
            if existing is None:
                await pdb.project_credits.insert_one(dict(credit_doc), session=session)
                credit_id = credit_doc["_id"]
                status = "registered"
            else:
                credit_id = existing["_id"]
                await pdb.project_credits.update_one(
                    {"_id": credit_id},
                    {
                        "$set": {
                            "name": credit_doc["name"],
                            "source_url": credit_doc.get("source_url"),
                            "updated_at": now,
                        }
                    },
                    session=session,
                )
                status = "updated"
            outbox_id = await enqueue_outbox_event(
                db,
                event_type="credit.license_resolve",
                payload={
                    "credit_id": credit_id,
                    "identifier": credit_doc["identifier"],
                    "kind": credit_doc["kind"],
                    "status": status,
                },
                workspace_id=workspace_id,
                project_id=project_id,
                session=session,
            )
            inv_doc["credit_id"] = credit_id
            inv_doc["outbox_id"] = outbox_id
        await db["projects"].update_one(
            {
                "_id": project_id,
                "workspace_id": workspace_id,
                "deleted_at": None,
            },
            {"$set": {"kaggle_data": inv_doc, "updated_at": now}},
            session=session,
        )
        return inv_doc

    async with client.start_session() as session:
        return await session.with_transaction(_txn)


async def hydrate_brain_store(
    db: AsyncDatabase, workspace_id: str, project_id: str
) -> CampaignBrainStore | None:
    """Transient store for advise/query — not the process-global BRAIN_STORE."""
    proj = await get_project(db, workspace_id, project_id)
    if proj is None:
        return None
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    store = CampaignBrainStore()
    store.projects[project_id] = proj
    store.by_org.setdefault(workspace_id, []).append(project_id)
    store.goals[project_id] = await pdb.list_goal_docs()
    store.experiments[project_id] = await pdb.list_experiment_docs()
    store.missions[project_id] = await pdb.list_mission_docs()
    store.dead_ends[project_id] = await pdb.list_dead_end_docs()
    store.episode_cards[project_id] = [
        doc async for doc in pdb.episode_cards.find({})
    ]
    store.axioms[project_id] = [doc async for doc in pdb.axioms.find({})]
    return store


async def publish_snapshot(
    db: AsyncDatabase,
    *,
    workspace_id: str,
    org_slug: str,
    project_id: str,
    include_goals: bool = True,
    include_lever_stats: bool = True,
    include_dead_end_lessons: bool = False,
) -> PublicSnapshotResponse | None:
    from mymlfw.saas.public_share import build_redacted_snapshot, make_share_slug

    proj = await get_project(db, workspace_id, project_id)
    if proj is None:
        return None
    dash = await load_dashboard(db, workspace_id, project_id)
    assert dash is not None
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    goals = await pdb.list_goal_docs() if include_goals else []
    dead_ends = await pdb.list_dead_end_docs()
    entropy = secrets.token_urlsafe(9)
    slug = make_share_slug(proj["slug"], entropy)
    redacted = build_redacted_snapshot(
        project=proj,
        dashboard=dash,
        goals=goals,
        dead_ends=dead_ends,
        include_goals=include_goals,
        include_lever_stats=include_lever_stats,
        include_dead_end_lessons=include_dead_end_lessons,
    )
    snap_id = new_snapshot_id()
    now = _utcnow()
    doc = {
        "_id": snap_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "schema_version": 1,
        "slug": slug,
        "org_slug": org_slug,
        "project_slug": proj["slug"],
        "entropy": entropy,
        "redacted": redacted,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
    await db["public_snapshots"].insert_one(doc)
    await db["projects"].update_one(
        {"_id": project_id, "workspace_id": workspace_id},
        {"$set": {"public_share_slug": slug, "updated_at": now}},
    )
    return PublicSnapshotResponse(
        slug=slug,
        org_slug=org_slug,
        project_slug=proj["slug"],
        share_path=f"/p/{org_slug}/{slug}",
        redacted=redacted,
        entropy=entropy,
    )


async def get_public_snapshot(
    db: AsyncDatabase, org_slug: str, slug: str
) -> dict[str, Any] | None:
    doc = await db["public_snapshots"].find_one(
        {"slug": slug, "org_slug": org_slug, "deleted_at": None}
    )
    return doc


async def create_project_stub(
    db: AsyncDatabase,
    *,
    workspace_id: str,
    name: str,
    kind: ProjectKind = ProjectKind.standalone,
) -> ProjectSummary:
    """Minimal project insert (wizard create lands later; used by tests)."""
    project_id = new_project_id()
    now = _utcnow()
    slug = name[:48].lower().replace(" ", "-")
    project = {
        "_id": project_id,
        "workspace_id": workspace_id,
        "project_id": project_id,
        "schema_version": 1,
        "slug": slug,
        "name": name,
        "kind": kind.value,
        "is_demo": False,
        "epoch_id": "epoch_0",
        "folds_sha256": secrets.token_hex(32),
        "adv_auc": None,
        "n_folds": 5,
        "folds_artifact_key": f"projects/{project_id}/folds.parquet",
        "public_share_slug": None,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
    }
    await db["projects"].insert_one(project)
    return project_summary_from_doc(project)


async def create_project(
    db: AsyncDatabase, *, workspace_id: str, body: Any
) -> ProjectSummary:
    from mymlfw.saas.studio import build_project_bundle

    project, goals = build_project_bundle(workspace_id=workspace_id, body=body)
    await db["projects"].insert_one(project)
    if goals:
        await db["project_goals"].insert_many(goals)
    return project_summary_from_doc(project)


async def archive_project(
    db: AsyncDatabase, *, workspace_id: str, project_id: str
) -> Any:
    from pymongo import ReturnDocument

    from mymlfw.saas.schemas import ProjectArchiveResponse

    now = _utcnow()
    result = await db["projects"].find_one_and_update(
        {
            "_id": project_id,
            "workspace_id": workspace_id,
            "deleted_at": None,
        },
        {"$set": {"deleted_at": now, "updated_at": now}},
        return_document=ReturnDocument.AFTER,
    )
    if result is None:
        raise KeyError("project_not_found")
    return ProjectArchiveResponse(id=project_id, deleted_at=now)


async def invite_member(
    db: AsyncDatabase,
    *,
    workspace_id: str,
    project_id: str,
    body: Any,
    user_id: str | None = None,
) -> Any:
    from mymlfw.saas.studio import build_invite_doc, member_from_doc

    proj = await get_project(db, workspace_id, project_id)
    if proj is None:
        raise KeyError("project_not_found")
    doc = build_invite_doc(
        workspace_id=workspace_id,
        project_id=project_id,
        body=body,
        user_id=user_id,
    )
    await db["project_members"].insert_one(doc)
    return member_from_doc(doc)


async def list_members(
    db: AsyncDatabase, workspace_id: str, project_id: str
) -> list[Any]:
    from mymlfw.saas.studio import member_from_doc

    if await get_project(db, workspace_id, project_id) is None:
        raise KeyError("project_not_found")
    cursor = db["project_members"].find(
        {
            "workspace_id": workspace_id,
            "project_id": project_id,
            "deleted_at": None,
        }
    ).sort("created_at", -1)
    return [member_from_doc(doc) async for doc in cursor]


async def list_goals(
    db: AsyncDatabase, workspace_id: str, project_id: str
) -> list[Any]:
    from mymlfw.saas.studio import goal_from_doc

    if await get_project(db, workspace_id, project_id) is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    return [goal_from_doc(g) for g in await pdb.list_goal_docs()]


async def add_goal(
    db: AsyncDatabase, *, workspace_id: str, project_id: str, body: Any
) -> Any:
    from mymlfw.saas.studio import build_goal_doc, goal_from_doc

    if await get_project(db, workspace_id, project_id) is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    doc = build_goal_doc(
        workspace_id=workspace_id, project_id=project_id, body=body
    )
    await pdb.goals.insert_one(doc)
    return goal_from_doc(doc)


async def update_goal(
    db: AsyncDatabase,
    *,
    workspace_id: str,
    project_id: str,
    goal_id: str,
    body: Any,
) -> Any:
    from mymlfw.saas.studio import apply_goal_update, goal_from_doc

    if await get_project(db, workspace_id, project_id) is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    doc = await pdb.goals.find_one({"_id": goal_id})
    if doc is None:
        raise KeyError("goal_not_found")
    apply_goal_update(doc, body)
    await pdb.goals.update_one(
        {"_id": goal_id},
        {
            "$set": {
                k: v
                for k, v in doc.items()
                if k not in {"_id", "workspace_id", "project_id"}
            }
        },
    )
    return goal_from_doc(doc)


async def list_progress(
    db: AsyncDatabase, workspace_id: str, project_id: str
) -> list[Any]:
    from mymlfw.saas.studio import progress_from_doc

    if await get_project(db, workspace_id, project_id) is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    cursor = pdb.progress.find({}).sort("created_at", -1)
    return [progress_from_doc(doc) async for doc in cursor]


async def add_progress(
    db: AsyncDatabase, *, workspace_id: str, project_id: str, body: Any
) -> Any:
    from mymlfw.saas.studio import build_progress_doc, progress_from_doc

    if await get_project(db, workspace_id, project_id) is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    doc = build_progress_doc(
        workspace_id=workspace_id, project_id=project_id, body=body
    )
    await pdb.progress.insert_one(doc)
    return progress_from_doc(doc)


async def list_dead_ends(
    db: AsyncDatabase, workspace_id: str, project_id: str
) -> list[Any]:
    from mymlfw.saas.studio import dead_end_from_doc

    if await get_project(db, workspace_id, project_id) is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    return [dead_end_from_doc(d) for d in await pdb.list_dead_end_docs()]


async def add_dead_end(
    db: AsyncDatabase, *, workspace_id: str, project_id: str, body: Any
) -> Any:
    from mymlfw.saas.studio import build_dead_end_doc, dead_end_from_doc

    proj = await get_project(db, workspace_id, project_id)
    if proj is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    doc = build_dead_end_doc(
        workspace_id=workspace_id,
        project_id=project_id,
        body=body,
        epoch_id=proj.get("epoch_id"),
    )
    await pdb.dead_ends.insert_one(doc)
    return dead_end_from_doc(doc)


async def list_sources(
    db: AsyncDatabase, workspace_id: str, project_id: str
) -> list[Any]:
    from mymlfw.saas.studio import source_from_doc

    if await get_project(db, workspace_id, project_id) is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    cursor = pdb.sources.find({}).sort("created_at", -1)
    return [source_from_doc(doc) async for doc in cursor]


async def add_source(
    db: AsyncDatabase, *, workspace_id: str, project_id: str, body: Any
) -> Any:
    from mymlfw.saas.studio import build_source_doc, source_from_doc

    if await get_project(db, workspace_id, project_id) is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    doc = build_source_doc(
        workspace_id=workspace_id, project_id=project_id, body=body
    )
    await pdb.sources.insert_one(doc)
    return source_from_doc(doc)


async def update_source(
    db: AsyncDatabase,
    *,
    workspace_id: str,
    project_id: str,
    source_id: str,
    body: Any,
) -> Any:
    from mymlfw.saas.studio import apply_source_update, source_from_doc

    if await get_project(db, workspace_id, project_id) is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    doc = await pdb.sources.find_one({"_id": source_id})
    if doc is None:
        raise KeyError("source_not_found")
    apply_source_update(doc, body)
    await pdb.sources.update_one(
        {"_id": source_id},
        {
            "$set": {
                k: v
                for k, v in doc.items()
                if k not in {"_id", "workspace_id", "project_id"}
            }
        },
    )
    return source_from_doc(doc)


async def delete_source(
    db: AsyncDatabase,
    *,
    workspace_id: str,
    project_id: str,
    source_id: str,
) -> bool:
    from datetime import UTC, datetime

    if await get_project(db, workspace_id, project_id) is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    result = await pdb.sources.update_one(
        {"_id": source_id},
        {"$set": {"deleted_at": datetime.now(UTC)}},
    )
    if not result.modified_count:
        raise KeyError("source_not_found")
    return True


async def list_roadmap_strategies(
    db: AsyncDatabase, workspace_id: str, project_id: str
) -> list[Any]:
    from mymlfw.saas.studio import roadmap_strategy_from_doc

    if await get_project(db, workspace_id, project_id) is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    cursor = pdb.roadmap_strategies.find({}).sort(
        [("priority", 1), ("created_at", -1)]
    )
    return [roadmap_strategy_from_doc(doc) async for doc in cursor]


async def add_roadmap_strategy(
    db: AsyncDatabase, *, workspace_id: str, project_id: str, body: Any
) -> Any:
    from mymlfw.saas.studio import build_roadmap_strategy_doc, roadmap_strategy_from_doc

    if await get_project(db, workspace_id, project_id) is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    doc = build_roadmap_strategy_doc(
        workspace_id=workspace_id, project_id=project_id, body=body
    )
    await pdb.roadmap_strategies.insert_one(doc)
    return roadmap_strategy_from_doc(doc)


async def update_roadmap_strategy(
    db: AsyncDatabase,
    *,
    workspace_id: str,
    project_id: str,
    strategy_id: str,
    body: Any,
) -> Any:
    from mymlfw.saas.studio import apply_roadmap_strategy_update, roadmap_strategy_from_doc

    if await get_project(db, workspace_id, project_id) is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    doc = await pdb.roadmap_strategies.find_one({"_id": strategy_id})
    if doc is None:
        raise KeyError("roadmap_strategy_not_found")
    apply_roadmap_strategy_update(doc, body)
    await pdb.roadmap_strategies.update_one(
        {"_id": strategy_id},
        {
            "$set": {
                k: v
                for k, v in doc.items()
                if k not in {"_id", "workspace_id", "project_id"}
            }
        },
    )
    return roadmap_strategy_from_doc(doc)


async def delete_roadmap_strategy(
    db: AsyncDatabase,
    *,
    workspace_id: str,
    project_id: str,
    strategy_id: str,
) -> bool:
    from datetime import UTC, datetime

    if await get_project(db, workspace_id, project_id) is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    result = await pdb.roadmap_strategies.update_one(
        {"_id": strategy_id},
        {"$set": {"deleted_at": datetime.now(UTC)}},
    )
    if not result.modified_count:
        raise KeyError("roadmap_strategy_not_found")
    return True


def _git_response(project_id: str, proj: dict[str, Any]) -> Any:
    from mymlfw.saas.schemas import ProjectGitInfo, ProjectGitResponse

    remote = (proj.get("git_remote") or "").strip()
    raw = proj.get("git_info")
    info = None
    if isinstance(raw, dict) and raw.get("remote"):
        info = ProjectGitInfo(**{k: v for k, v in raw.items() if k in ProjectGitInfo.model_fields})
    elif remote:
        info = ProjectGitInfo(remote=remote)
    return ProjectGitResponse(
        project_id=project_id,
        linked=bool(remote),
        git=info,
    )


async def get_project_git(
    db: AsyncDatabase, workspace_id: str, project_id: str
) -> Any:
    proj = await get_project(db, workspace_id, project_id)
    if proj is None:
        raise KeyError("project_not_found")
    return _git_response(project_id, proj)


async def set_project_git(
    db: AsyncDatabase,
    *,
    workspace_id: str,
    project_id: str,
    remote: str,
    refresh: bool = True,
) -> Any:
    from datetime import UTC, datetime

    from mymlfw.saas.git_info import build_git_info

    proj = await get_project(db, workspace_id, project_id)
    if proj is None:
        raise KeyError("project_not_found")
    info = build_git_info(remote, live=refresh)
    now = datetime.now(UTC)
    await db["projects"].update_one(
        {"_id": project_id, "workspace_id": workspace_id, "deleted_at": None},
        {
            "$set": {
                "git_remote": info["remote"],
                "git_info": info,
                "updated_at": now,
            }
        },
    )
    proj["git_remote"] = info["remote"]
    proj["git_info"] = info
    return _git_response(project_id, proj)


async def refresh_project_git(
    db: AsyncDatabase, *, workspace_id: str, project_id: str
) -> Any:
    from datetime import UTC, datetime

    from mymlfw.saas.git_info import build_git_info

    proj = await get_project(db, workspace_id, project_id)
    if proj is None:
        raise KeyError("project_not_found")
    remote = (proj.get("git_remote") or "").strip()
    if not remote:
        raise KeyError("git_not_linked")
    linked_at = None
    if isinstance(proj.get("git_info"), dict):
        linked_at = proj["git_info"].get("linked_at")
    info = build_git_info(remote, live=True)
    if linked_at is not None:
        info["linked_at"] = linked_at
    now = datetime.now(UTC)
    await db["projects"].update_one(
        {"_id": project_id, "workspace_id": workspace_id, "deleted_at": None},
        {"$set": {"git_info": info, "updated_at": now}},
    )
    proj["git_info"] = info
    return _git_response(project_id, proj)


async def clear_project_git(
    db: AsyncDatabase, *, workspace_id: str, project_id: str
) -> Any:
    from datetime import UTC, datetime

    proj = await get_project(db, workspace_id, project_id)
    if proj is None:
        raise KeyError("project_not_found")
    now = datetime.now(UTC)
    await db["projects"].update_one(
        {"_id": project_id, "workspace_id": workspace_id, "deleted_at": None},
        {
            "$set": {"git_remote": None, "git_info": None, "updated_at": now},
        },
    )
    proj["git_remote"] = None
    proj["git_info"] = None
    return _git_response(project_id, proj)


async def list_levers(
    db: AsyncDatabase, workspace_id: str, project_id: str
) -> list[Any]:
    from mymlfw.saas.studio import experiment_from_doc

    if await get_project(db, workspace_id, project_id) is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    return [experiment_from_doc(e) for e in await pdb.list_experiment_docs()]


async def open_lever(
    db: AsyncDatabase, *, workspace_id: str, project_id: str, body: Any
) -> Any:
    from datetime import timedelta

    from mymlfw.saas.studio import build_experiment_doc, experiment_from_doc, lock_expires

    proj = await get_project(db, workspace_id, project_id)
    if proj is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    open_n = sum(
        1
        for e in await pdb.list_experiment_docs()
        if e.get("status") == "open"
    )
    if open_n >= 1:
        raise RuntimeError("one_open_lever")
    goals = await pdb.list_goal_docs()
    goal_ids = {g.get("_id") or g.get("id") for g in goals}
    if body.goal_id not in goal_ids:
        raise KeyError("goal_not_found")
    doc = build_experiment_doc(
        workspace_id=workspace_id,
        project_id=project_id,
        body=body,
        epoch_id=proj.get("epoch_id"),
    )
    try:
        await pdb.acquire_execution_lock(
            holder_type="lever",
            holder_id=doc["_id"],
            expires_at=lock_expires(),
        )
    except RuntimeError as exc:
        raise RuntimeError("one_open_lever") from exc
    await pdb.experiments.insert_one(doc)
    _ = timedelta  # kept for clarity with lock_expires
    return experiment_from_doc(doc)


async def close_lever(
    db: AsyncDatabase,
    *,
    workspace_id: str,
    project_id: str,
    experiment_id: str,
    body: Any,
) -> Any:
    from mymlfw.saas.studio import apply_lever_close, experiment_from_doc

    if await get_project(db, workspace_id, project_id) is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    doc = await pdb.experiments.find_one({"_id": experiment_id})
    if doc is None:
        raise KeyError("lever_not_found")
    try:
        apply_lever_close(doc, body)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    await pdb.experiments.update_one(
        {"_id": experiment_id},
        {
            "$set": {
                k: v
                for k, v in doc.items()
                if k not in {"_id", "workspace_id", "project_id"}
            }
        },
    )
    await pdb.release_execution_lock(
        holder_type="lever", holder_id=experiment_id
    )
    return experiment_from_doc(doc)


async def list_missions(
    db: AsyncDatabase, workspace_id: str, project_id: str
) -> list[Any]:
    from mymlfw.saas.studio import mission_from_doc

    if await get_project(db, workspace_id, project_id) is None:
        raise KeyError("project_not_found")
    pdb = ProjectScopedDB(db, workspace_id=workspace_id, project_id=project_id)
    return [mission_from_doc(m) for m in await pdb.list_mission_docs()]
