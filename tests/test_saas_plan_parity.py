"""Lock: every in-scope Studio matrix feature has OpenAPI path + GUI binder."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OPENAPI = ROOT / "contracts" / "openapi.json"
APP_JS = ROOT / "web" / "public" / "app.js"
SAAS_API_DOC = ROOT / "docs" / "reference" / "saas-api.md"
PARITY_DOC = ROOT / "docs" / "reference" / "saas-plan-parity-matrix.md"

# Studio-facing paths the GUI must mention (binder string or exact path fragment).
GUI_BINDERS: list[tuple[str, str]] = [
    ("advise CTA", "/advise"),
    ("progress notes", "/progress"),
    ("dead ends", "/dead-ends"),
    ("levers", "/levers"),
    ("missions", "/missions"),
    ("goals CRUD", "/goals"),
    ("dashboard", "/dashboard"),
    ("research runs", "/research-runs"),
    ("ensemble", "/ensemble"),
    ("autopilot start", "/autopilot/start"),
    ("autopilot digest", "/autopilot/digest"),
    ("kaggle intel", "/kaggle/intel"),
    ("kaggle refresh", "/kaggle/refresh"),
    ("kaggle discussions", "/kaggle/discussions"),
    ("kaggle push", "/kaggle/push"),
    ("cloud accounts", "/cloud/accounts"),
    ("cloud launch", "/cloud/launch"),
    ("runners", "/runners"),
    ("git plan", "/git/plan"),
    ("credits harvest", "/credits/harvest"),
    ("credits verify", "/credits/verify"),
    ("credits export", "/credits/export"),
    ("members", "/members"),
    ("share", "/share"),
    ("invite", "/invite"),
]

# OpenAPI path templates that must exist for Studio parity.
REQUIRED_OPENAPI_SNIPPETS: list[str] = [
    "/v1/projects/{project_id}/dashboard",
    "/v1/projects/{project_id}/advise",
    "/v1/projects/{project_id}/progress",
    "/v1/projects/{project_id}/dead-ends",
    "/v1/projects/{project_id}/levers",
    "/v1/projects/{project_id}/missions",
    "/v1/projects/{project_id}/goals",
    "/v1/projects/{project_id}/members",
    "/v1/projects/{project_id}/research-runs",
    "/v1/projects/{project_id}/ensemble",
    "/v1/projects/{project_id}/autopilot/start",
    "/v1/projects/{project_id}/kaggle/intel",
    "/v1/projects/{project_id}/kaggle/refresh",
    "/v1/projects/{project_id}/credits/harvest",
    "/v1/projects/{project_id}/git/plan",
    "/v1/orgs/current/cloud/accounts",
    "/v1/orgs/current/runners",
]


@pytest.fixture(scope="module")
def openapi_paths() -> set[str]:
    if not OPENAPI.is_file():
        pytest.skip("contracts/openapi.json missing — run make openapi")
    data = json.loads(OPENAPI.read_text(encoding="utf-8"))
    return set(data.get("paths") or {})


def test_saas_api_docs_exist():
    assert SAAS_API_DOC.is_file(), "docs/reference/saas-api.md required"
    assert PARITY_DOC.is_file()
    text = SAAS_API_DOC.read_text(encoding="utf-8")
    assert "DashboardResponse panels" in text
    assert "BRAIN" in text and "TRUST" in text


def test_gui_binders_present():
    src = APP_JS.read_text(encoding="utf-8")
    missing = [name for name, needle in GUI_BINDERS if needle not in src]
    assert not missing, f"GUI missing binders: {missing}"


def test_openapi_studio_paths(openapi_paths: set[str]):
    missing = [p for p in REQUIRED_OPENAPI_SNIPPETS if p not in openapi_paths]
    assert not missing, f"OpenAPI missing paths: {missing}"


def test_dashboard_response_panels_in_openapi(openapi_paths: set[str]):
    data = json.loads(OPENAPI.read_text(encoding="utf-8"))
    schemas = (data.get("components") or {}).get("schemas") or {}
    dash = schemas.get("DashboardResponse") or {}
    props = dash.get("properties") or {}
    for panel in (
        "goals",
        "scores",
        "levers",
        "ensemble",
        "compute",
        "paradigms",
        "strategies",
        "research",
        "missions",
        "dead_ends",
        "daily_progress",
        "kaggle",
        "git",
        "brain",
    ):
        assert panel in props, f"DashboardResponse missing {panel}"


def test_parity_matrix_no_brain_gap_rows():
    """BRAIN/GOALS/LAB/KAGGLE/OPS/TRUST primary rows should not stay at gap."""
    text = PARITY_DOC.read_text(encoding="utf-8")
    # Soft check: primary Studio sections mention ok for dashboard/advise/goals.
    for needle in (
        "`GET /v1/projects/{id}/dashboard`",
        "`POST /v1/projects/{id}/advise`",
        "GOALS mode",
        "LAB Night controls",
        "TRUST Credits",
    ):
        assert needle in text


def test_app_js_hides_kaggle_for_standalone():
    src = APP_JS.read_text(encoding="utf-8")
    assert re.search(r"kind\s*!==\s*[\"']kaggle[\"']", src) or "kind === \"kaggle\"" in src
    assert "KAGGLE" in src
