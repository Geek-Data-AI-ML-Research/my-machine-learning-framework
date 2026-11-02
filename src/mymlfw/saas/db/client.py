"""AsyncMongoClient factory with tz-aware codecs, Decimal128, zstd, majority."""

from __future__ import annotations

from datetime import UTC
from typing import Any

from bson.binary import BinaryVector, BinaryVectorDtype
from bson.codec_options import CodecOptions, TypeCodec, TypeRegistry
from bson.decimal128 import Decimal128
from pymongo import AsyncMongoClient, ReadPreference, WriteConcern
from pymongo.read_concern import ReadConcern


class _DecimalCodec(TypeCodec):
    python_type = float  # type: ignore[assignment]
    bson_type = Decimal128

    def transform_python(self, value: float) -> Decimal128:
        return Decimal128(str(value))

    def transform_bson(self, value: Decimal128) -> Decimal128:
        return value


def _saas_codec_options() -> CodecOptions:
    registry = TypeRegistry([_DecimalCodec()])
    return CodecOptions(tz_aware=True, tzinfo=UTC, type_registry=registry)


def create_saas_mongo_client(
    uri: str,
    *,
    appname: str = "mymlfw-saas",
) -> AsyncMongoClient:
    """Build the shared control-plane Mongo client (never Motor).

    Ensures ``compressors=zstd`` on the URI when missing, majority R/W,
    and tz-aware UTC ``CodecOptions``.
    """
    if "compressors=" not in uri:
        sep = "&" if "?" in uri else "?"
        uri = f"{uri}{sep}compressors=zstd"

    client: AsyncMongoClient = AsyncMongoClient(
        uri,
        appname=appname,
        tz_aware=True,
        tzinfo=UTC,
        codec_options=_saas_codec_options(),
        w="majority",
        readConcernLevel="majority",
        # Explicit defaults mirrored for callers that inspect kwargs later.
        write_concern=WriteConcern(w="majority"),
        read_preference=ReadPreference.PRIMARY,
        read_concern=ReadConcern(level="majority"),
    )
    return client


def pack_embedding_f32(values: list[float] | tuple[float, ...]) -> BinaryVector:
    """Pack a dense float embedding as BSON BinaryVector FLOAT32 (not list[float])."""
    if not values:
        raise ValueError("embedding must be non-empty")
    for v in values:
        if v != v or v in (float("inf"), float("-inf")):  # NaN / Inf
            raise ValueError("embedding values must be finite")
    return BinaryVector(list(values), BinaryVectorDtype.FLOAT32)


def client_codec_is_tz_aware(client: AsyncMongoClient) -> bool:
    """Test helper: codec options used by the client are tz-aware UTC."""
    opts: CodecOptions = client.codec_options  # type: ignore[assignment]
    return bool(opts.tz_aware) and opts.tzinfo is UTC


def describe_client_defaults() -> dict[str, Any]:
    """Document locked client defaults for OpenAPI / ops stubs."""
    return {
        "driver": "pymongo.AsyncMongoClient",
        "tz_aware": True,
        "tzinfo": "UTC",
        "compressors": "zstd",
        "write_concern": "majority",
        "read_concern": "majority",
    }
