"""BSON shapes for Kaggle intel/data/credits (tz-aware dates, finite metrics, bytes)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mymlfw.saas.db.kaggle_docs import (
    credit_doc_for_mongo,
    envelope_blob_for_mongo,
    finite_float,
    intel_doc_for_mongo,
    inventory_doc_for_mongo,
    normalize_leaderboard_row,
    parse_utc,
)
from mymlfw.saas.kaggle_service import refresh_intel_cache, seal_kaggle_token
from mymlfw.saas.schemas import LicenseStatus


def test_parse_utc_and_finite() -> None:
    assert parse_utc("2026-11-02T13:45:31.777903+00:00").tzinfo is not None
    assert parse_utc("2026-11-01 21:05:13").year == 2026
    assert finite_float("27.99617") == pytest.approx(27.99617)
    assert finite_float("nan") is None
    assert finite_float("inf") is None


def test_leaderboard_strips_bom_and_types() -> None:
    row = normalize_leaderboard_row(
        {
            "\ufeffRank": "1",
            "TeamName": "alpha",
            "Score": "27.9",
            "LastSubmissionDate": "2026-11-01 21:05:13",
            "SubmissionCount": "20",
        }
    )
    assert row["rank"] == 1
    assert row["score"] == pytest.approx(27.9)
    assert isinstance(row["last_submission_at"], datetime)
    assert row["last_submission_at"].tzinfo is not None


def test_intel_doc_uses_bson_dates_not_iso_strings() -> None:
    panel = refresh_intel_cache(
        competition="google-verifiable-quantum-circuit-compilation",
        files=[{"name": "a.csv", "totalBytes": "12", "creationDate": "2026-10-22T17:40:15.057Z"}],
        leaderboard=[{"Rank": "1", "TeamName": "t", "Score": "1.5"}],
        kernels=[{"ref": "u/k", "title": "K", "lastRunTime": "2026-10-01T00:00:00Z"}],
        rank=887,
        public_score=float("nan"),
        refreshed_by="kaggle_api",
    )
    assert isinstance(panel["last_sync"], datetime)
    doc = intel_doc_for_mongo(panel)
    assert isinstance(doc["last_sync"], datetime)
    assert doc["last_sync"].tzinfo is not None
    assert doc["public_score"] is None  # NaN dropped
    assert doc["rank"] == 887
    assert doc["files"][0]["total_bytes"] == 12
    assert isinstance(doc["files"][0]["created_at"], datetime)
    assert doc["leaderboard"][0]["score"] == pytest.approx(1.5)
    assert doc["schema_version"] == 1


def test_inventory_and_credit_docs() -> None:
    inv = inventory_doc_for_mongo(
        {
            "competition": "c",
            "files": [{"name": "x", "totalBytes": 3}],
            "downloaded": {"path": "/data/x.zip", "bytes": 9, "file_name": "x.zip"},
            "imported_at": "2026-11-02T13:45:38.004048+00:00",
            "credit_id": "crd_01TEST",
        }
    )
    assert isinstance(inv["imported_at"], datetime)
    assert inv["downloaded"]["bytes"] == 9

    credit = credit_doc_for_mongo(
        {
            "_id": "crd_01TEST",
            "kind": "kaggle_dataset",
            "identifier": "kaggle://competitions/c",
            "identifier_key": "kaggle_dataset:kaggle://competitions/c",
            "name": "kaggle:c",
            "license_status": "UNVERIFIED_LICENSE",
            "harvest_source": "agent",
        }
    )
    assert credit["license_status"] == LicenseStatus.unverified.value
    assert credit["deleted_at"] is None
    assert isinstance(credit["created_at"], datetime)
    assert "source" not in credit  # legacy free-form field not stored


def test_envelope_blob_requires_bytes() -> None:
    sealed = seal_kaggle_token("KGAT_test")
    blob = envelope_blob_for_mongo(sealed["_blob"])
    assert isinstance(blob["ciphertext"], bytes)
    assert isinstance(blob["nonce"], bytes)
    with pytest.raises(TypeError):
        envelope_blob_for_mongo(
            {
                "ciphertext": "deadbeef",
                "nonce": "",
                "kek_version": 1,
                "cipher_alg": "aes-256-gcm",
            }
        )


@pytest.mark.asyncio
async def test_mongo_roundtrip_kaggle_intel_types() -> None:
    import os
    import uuid

    uri = os.environ.get("MYMLFW_MONGO_URI", "").strip()
    if not uri:
        uri = "mongodb://127.0.0.1:27017/?directConnection=true"
    try:
        from mymlfw.saas.db.client import create_saas_mongo_client, get_saas_database
    except Exception:
        pytest.skip("pymongo unavailable")

    client = create_saas_mongo_client(uri)
    try:
        await client.admin.command("ping")
    except Exception:
        await client.close()
        pytest.skip("mongo unavailable")

    from mymlfw.saas.db import project_data
    from mymlfw.saas.db.indexes import ensure_saas_indexes
    from mymlfw.saas.db.migrations import run_migrations
    from mymlfw.saas.schemas import GoalKind, ProjectCreate, ProjectGoalCreate, ProjectKind

    db_name = f"mymlfw_kaggle_{uuid.uuid4().hex[:8]}"
    db = get_saas_database(client, db_name)
    await run_migrations(db)
    await ensure_saas_indexes(db)
    try:
        org = f"org_{uuid.uuid4().hex[:10]}"
        summary = await project_data.create_project(
            db,
            workspace_id=org,
            body=ProjectCreate(
                name="VQCC",
                kind=ProjectKind.kaggle,
                kaggle_competition="google-verifiable-quantum-circuit-compilation",
                goals=[
                    ProjectGoalCreate(
                        title="public LB",
                        kind=GoalKind.kaggle_public,
                        threshold=0.7,
                    )
                ],
            ),
        )
        pid = summary.id
        panel = refresh_intel_cache(
            competition="google-verifiable-quantum-circuit-compilation",
            files=[{"name": "train.csv", "totalBytes": 10}],
            leaderboard=[{"Rank": "2", "Score": "1.25", "TeamName": "us"}],
            rank=2,
            public_score=1.25,
            refreshed_by="kaggle_api",
        )
        stored = await project_data.store_project_kaggle_intel(
            db, workspace_id=org, project_id=pid, panel=panel
        )
        assert isinstance(stored["last_sync"], datetime)

        proj = await project_data.get_project(db, org, pid)
        intel = proj["kaggle_intel"]
        assert isinstance(intel["last_sync"], datetime)
        assert intel["last_sync"].tzinfo is not None
        assert intel["public_score"] == pytest.approx(1.25)

        sealed = seal_kaggle_token("KGAT_roundtrip")
        await project_data.store_project_kaggle_token(
            db, workspace_id=org, project_id=pid, blob=sealed["_blob"]
        )
        proj2 = await project_data.get_project(db, org, pid)
        blob = proj2["kaggle_token_blob"]
        assert isinstance(blob["ciphertext"], (bytes, bytearray))
        assert isinstance(blob["nonce"], (bytes, bytearray))

        result = await project_data.store_project_kaggle_data(
            db,
            workspace_id=org,
            project_id=pid,
            inventory={
                "competition": "google-verifiable-quantum-circuit-compilation",
                "files": [{"name": "train.csv", "totalBytes": 10}],
                "downloaded": {"path": "/tmp/x.zip", "bytes": 99, "file_name": "x.zip"},
                "imported_at": datetime.now(UTC),
            },
            credit={
                "_id": f"crd_{uuid.uuid4().hex[:16].upper()}",
                "kind": "kaggle_dataset",
                "identifier": "kaggle://competitions/google-verifiable-quantum-circuit-compilation",
                "identifier_key": (
                    "kaggle_dataset:kaggle://competitions/"
                    "google-verifiable-quantum-circuit-compilation"
                ),
                "name": "kaggle:vqcc",
                "license_status": "UNVERIFIED_LICENSE",
                "harvest_source": "agent",
            },
        )
        assert isinstance(result["imported_at"], datetime)
        assert result.get("outbox_id", "").startswith("obx_")
        credit = await db["project_credits"].find_one({"_id": result["credit_id"]})
        assert credit is not None
        assert credit["license_status"] == "UNVERIFIED_LICENSE"
        assert isinstance(credit["created_at"], datetime)
        outbox = await db["outbox_events"].find_one({"_id": result["outbox_id"]})
        assert outbox is not None
        assert outbox["event_type"] == "credit.license_resolve"
        assert isinstance(outbox["created_at"], datetime)
    finally:
        await client.drop_database(db_name)
        await client.close()
