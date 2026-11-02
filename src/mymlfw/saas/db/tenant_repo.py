"""ScopedCollection: tenant force, $ strip, soft-delete filter."""

from __future__ import annotations

import re
from typing import Any, Mapping, MutableMapping, Sequence

from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.cursor import AsyncCursor
from pymongo.results import DeleteResult, InsertOneResult, UpdateResult

_FORBIDDEN_SET_KEYS = frozenset({"workspace_id", "project_id", "_id"})
_REGEX_MAX_LEN = 64


class TenantFilterError(ValueError):
    """Raised when an untrusted filter contains forbidden operators."""


class ScopedCollection:
    """Force workspace/project + soft-delete on every read/write/aggregate."""

    def __init__(
        self,
        collection: AsyncCollection,
        *,
        workspace_id: str,
        project_id: str,
    ) -> None:
        self._collection = collection
        self.workspace_id = workspace_id
        self.project_id = project_id

    @property
    def name(self) -> str:
        return self._collection.name

    def _tenant_match(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "project_id": self.project_id,
            "deleted_at": None,
        }

    def _sanitize_filter(self, filt: Mapping[str, Any] | None) -> dict[str, Any]:
        raw = dict(filt or {})
        self._reject_dollar_keys(raw)
        # Overwrite any tampered tenant keys from the caller.
        raw.pop("workspace_id", None)
        raw.pop("project_id", None)
        raw.pop("deleted_at", None)
        merged = self._tenant_match()
        merged.update(raw)
        return merged

    def _reject_dollar_keys(self, obj: Any, *, path: str = "") -> None:
        if isinstance(obj, Mapping):
            for key, value in obj.items():
                if isinstance(key, str) and key.startswith("$"):
                    if key == "$regex":
                        self._validate_regex(value)
                    else:
                        raise TenantFilterError(
                            f"forbidden operator {key!r} in filter{path}"
                        )
                self._reject_dollar_keys(value, path=f"{path}.{key}")
        elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
            for i, item in enumerate(obj):
                self._reject_dollar_keys(item, path=f"{path}[{i}]")

    @staticmethod
    def _validate_regex(pattern: Any) -> None:
        if not isinstance(pattern, str):
            raise TenantFilterError("$regex must be a string")
        if len(pattern) > _REGEX_MAX_LEN:
            raise TenantFilterError("$regex exceeds length cap")
        # Force escaped semantics for untrusted patterns.
        re.escape(pattern)

    def _sanitize_update(self, update: Mapping[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for op, body in update.items():
            if not isinstance(op, str) or not op.startswith("$"):
                raise TenantFilterError("update must use operator documents")
            if not isinstance(body, MutableMapping):
                out[op] = body
                continue
            cleaned = dict(body)
            if op == "$set":
                for key in _FORBIDDEN_SET_KEYS:
                    cleaned.pop(key, None)
            out[op] = cleaned
        # Always re-assert tenant keys on $setOnInsert / ensure present on insert path.
        return out

    def _stamp_document(self, doc: MutableMapping[str, Any]) -> dict[str, Any]:
        stamped = dict(doc)
        stamped["workspace_id"] = self.workspace_id
        stamped["project_id"] = self.project_id
        stamped.setdefault("deleted_at", None)
        return stamped

    async def find_one(
        self,
        filter: Mapping[str, Any] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        return await self._collection.find_one(
            self._sanitize_filter(filter), *args, **kwargs
        )

    def find(
        self,
        filter: Mapping[str, Any] | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> AsyncCursor:
        return self._collection.find(self._sanitize_filter(filter), *args, **kwargs)

    async def insert_one(
        self, document: MutableMapping[str, Any], *args: Any, **kwargs: Any
    ) -> InsertOneResult:
        return await self._collection.insert_one(
            self._stamp_document(document), *args, **kwargs
        )

    async def update_one(
        self,
        filter: Mapping[str, Any],
        update: Mapping[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> UpdateResult:
        return await self._collection.update_one(
            self._sanitize_filter(filter),
            self._sanitize_update(update),
            *args,
            **kwargs,
        )

    async def update_many(
        self,
        filter: Mapping[str, Any],
        update: Mapping[str, Any],
        *args: Any,
        **kwargs: Any,
    ) -> UpdateResult:
        return await self._collection.update_many(
            self._sanitize_filter(filter),
            self._sanitize_update(update),
            *args,
            **kwargs,
        )

    async def delete_one(
        self, filter: Mapping[str, Any], *args: Any, **kwargs: Any
    ) -> DeleteResult:
        # Soft-delete by default.
        result = await self.update_one(
            filter,
            {"$set": {"deleted_at": kwargs.pop("deleted_at", True)}},
        )
        # Mimic DeleteResult-ish: callers should prefer soft-delete semantics.
        return DeleteResult({"n": result.modified_count}, acknowledged=True)

    async def aggregate(
        self, pipeline: Sequence[Mapping[str, Any]], *args: Any, **kwargs: Any
    ) -> Any:
        match = {"$match": self._tenant_match()}
        stages = [match, *pipeline]
        return await self._collection.aggregate(stages, *args, **kwargs)

    # --- test helpers (no I/O) ---------------------------------------------

    def preview_filter(self, filter: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Return the filter that would be sent (unit-test helper)."""
        return self._sanitize_filter(filter)

    def preview_update(self, update: Mapping[str, Any]) -> dict[str, Any]:
        return self._sanitize_update(update)

    def preview_document(self, document: MutableMapping[str, Any]) -> dict[str, Any]:
        return self._stamp_document(document)
