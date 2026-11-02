"""AsyncMongoClient factory with tz-aware codecs, Decimal128, zstd, majority."""

from __future__ import annotations

from datetime import UTC
from decimal import Decimal
from typing import Any

from bson.binary import BinaryVector, BinaryVectorDtype
from bson.codec_options import CodecOptions, TypeCodec, TypeRegistry
from bson.decimal128 import Decimal128
from pymongo import AsyncMongoClient, ReadPreference


class _DecimalCodec(TypeCodec):
    """Encode ``decimal.Decimal`` as BSON Decimal128 (money-adjacent values)."""

    python_type = Decimal
    bson_type = Decimal128

    def transform_python(self, value: Decimal) -> Decimal128:
        return Decimal128(value)

    def transform_bson(self, value: Decimal128) -> Decimal:
        return value.to_decimal()


def saas_codec_options() -> CodecOptions:
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
        w="majority",
        readConcernLevel="majority",
        read_preference=ReadPreference.PRIMARY,
    )
    # Stash for get_saas_database / tests (client-level codec_options is read-only).
    client._mymlfw_codec_options = saas_codec_options()  # type: ignore[attr-defined]
    return client


def get_saas_database(client: AsyncMongoClient, name: str) -> Any:
    """Return a database handle with tz-aware UTC + Decimal128 codec options."""
    opts = getattr(client, "_mymlfw_codec_options", None) or saas_codec_options()
    return client.get_database(name, codec_options=opts)


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
    opts: CodecOptions = getattr(client, "_mymlfw_codec_options", None) or client.codec_options
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
