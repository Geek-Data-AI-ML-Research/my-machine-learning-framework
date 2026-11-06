"""Docs lock for saas-api.md + OpenAPI regenerate hygiene."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_saas_api_md_matrix_headers():
    text = (ROOT / "docs" / "reference" / "saas-api.md").read_text(encoding="utf-8")
    for section in ("BRAIN", "GOALS", "LAB", "KAGGLE", "OPS", "TRUST", "Studio home"):
        assert section in text
    assert "contracts/openapi.json" in text
    assert "web/public/app.js" in text


def test_openapi_contract_file_present():
    path = ROOT / "contracts" / "openapi.json"
    assert path.is_file()
    assert path.stat().st_size > 1000
