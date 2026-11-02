"""Zero-trust Mongo access for Campaign SaaS."""

from mymlfw.saas.db.client import (
    create_saas_mongo_client,
    get_saas_database,
    pack_embedding_f32,
    saas_codec_options,
)
from mymlfw.saas.db.indexes import ONE_OPEN_LEVER_INDEX, ensure_saas_indexes
from mymlfw.saas.db.project_db import ProjectScopedDB
from mymlfw.saas.db.tenant_repo import ScopedCollection

__all__ = [
    "ONE_OPEN_LEVER_INDEX",
    "ProjectScopedDB",
    "ScopedCollection",
    "create_saas_mongo_client",
    "ensure_saas_indexes",
    "get_saas_database",
    "pack_embedding_f32",
    "saas_codec_options",
]
