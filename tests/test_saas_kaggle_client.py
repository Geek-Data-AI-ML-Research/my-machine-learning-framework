"""Kaggle Public API client + sync helpers (mocked HTTP)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from mymlfw.saas.kaggle_client import (
    KaggleClientError,
    download_competition_data,
    fetch_competition_files,
    my_rank_from_leaderboard,
    resolve_kaggle_token,
)
from mymlfw.saas.kaggle_service import (
    import_competition_data,
    refresh_intel_cache,
    sync_competition_from_kaggle,
)


def test_resolve_token_prefers_sealed_then_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    monkeypatch.delenv("MYMLFW_KAGGLE_API_TOKEN", raising=False)
    assert resolve_kaggle_token(sealed_plaintext="  sealed  ") == "sealed"
    assert (
        resolve_kaggle_token(env={"KAGGLE_API_TOKEN": "KGAT_from_env"}) == "KGAT_from_env"
    )
    tok = tmp_path / "access_token"
    tok.write_text("KGAT_file\n", encoding="utf-8")
    monkeypatch.setattr(
        "mymlfw.saas.kaggle_client.Path.home", lambda: tmp_path.parent
    )
    # home/.kaggle/access_token — point home so ~/.kaggle resolves under tmp
    kaggle_home = tmp_path
    (kaggle_home / ".kaggle").mkdir()
    (kaggle_home / ".kaggle" / "access_token").write_text("KGAT_home", encoding="utf-8")
    monkeypatch.setattr("mymlfw.saas.kaggle_client.Path.home", lambda: kaggle_home)
    assert resolve_kaggle_token(env={}) == "KGAT_home"


def test_my_rank_requires_team_hint() -> None:
    rows = [{"Rank": "1", "TeamName": "alpha", "Score": "0.9"}]
    assert my_rank_from_leaderboard(rows) == (None, None)
    assert my_rank_from_leaderboard(rows, team_or_user="alpha") == (1, 0.9)


def test_fetch_files_and_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class _Resp:
        def __init__(self, *, status: int = 200, json_body=None, content=b"", text: str = "") -> None:
            self.status_code = status
            self._json = json_body
            self.content = content
            self.text = text

        def json(self):
            return self._json

        def read(self):
            return self.content

        def iter_bytes(self):
            yield self.content

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class _Client:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params=None):
            if "data/list" in url:
                return _Resp(json_body={"files": [{"name": "train.csv", "totalBytes": 12}]})
            raise AssertionError(url)

        def stream(self, method, url):
            assert method == "GET"
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("train.csv", "a,b\n1,2\n")
            return _Resp(content=buf.getvalue())

    monkeypatch.setattr(
        "mymlfw.saas.kaggle_client.assert_public_host", lambda host: ["1.2.3.4"]
    )
    monkeypatch.setattr("httpx.Client", _Client)
    files = fetch_competition_files("google-verifiable-quantum-circuit-compilation", token="KGAT_x")
    assert files[0]["name"] == "train.csv"
    out = download_competition_data(
        "google-verifiable-quantum-circuit-compilation",
        tmp_path,
        token="KGAT_x",
    )
    assert out.is_file() and out.stat().st_size > 0


def test_sync_and_import(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "mymlfw.saas.kaggle_client.fetch_competition",
        lambda competition, token="": {
            "titleNullable": "VQCC",
            "urlNullable": f"https://www.kaggle.com/competitions/{competition}",
            "userRankNullable": 42,
        },
    )
    monkeypatch.setattr(
        "mymlfw.saas.kaggle_client.fetch_competition_files",
        lambda competition, token="": [{"name": "train.csv", "totalBytes": 10}],
    )
    monkeypatch.setattr(
        "mymlfw.saas.kaggle_client.fetch_kernels",
        lambda competition, token="", page_size=20: [
            {"ref": "user/nb", "title": "Starter", "author": "user"}
        ],
    )
    monkeypatch.setattr(
        "mymlfw.saas.kaggle_client.fetch_leaderboard_rows",
        lambda competition, token="", limit=50: [
            {"Rank": "1", "TeamName": "top", "Score": "0.99"}
        ],
    )
    def _fake_download(competition, dest_dir, token="", file_name=None):
        root = Path(dest_dir)
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{competition}.zip"
        path.write_bytes(b"PK\x03\x04")
        return path

    monkeypatch.setattr(
        "mymlfw.saas.kaggle_client.download_competition_data",
        _fake_download,
    )
    monkeypatch.setenv("MYMLFW_KAGGLE_DATA_DIR", str(tmp_path))

    panel = sync_competition_from_kaggle(
        competition="google-verifiable-quantum-circuit-compilation",
        token="KGAT_x",
    )
    assert panel["refreshed_by"] == "kaggle_api"
    assert panel["rank"] == 42
    assert panel["files"][0]["name"] == "train.csv"
    assert panel["kernels"][0]["title"] == "Starter"

    result = import_competition_data(
        competition="google-verifiable-quantum-circuit-compilation",
        workspace_id="org_test",
        project_id="prj_test",
        token="KGAT_x",
        download=True,
    )
    assert result["inventory"]["files"][0]["name"] == "train.csv"
    assert result["credit"]["kind"] == "kaggle_dataset"
    assert Path(result["inventory"]["downloaded"]["path"]).is_file()

    cached = refresh_intel_cache(
        competition="demo", discussions=[], kernels=[], refreshed_by="client"
    )
    assert cached["refreshed_by"] == "client"


def test_missing_credentials_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "mymlfw.saas.kaggle_client.resolve_kaggle_basic", lambda env=None: None
    )
    monkeypatch.setattr(
        "mymlfw.saas.kaggle_client.assert_public_host", lambda host: ["1.2.3.4"]
    )
    with pytest.raises(KaggleClientError) as exc:
        fetch_competition_files("x", token="")
    assert exc.value.code == "kaggle_credentials_required"
