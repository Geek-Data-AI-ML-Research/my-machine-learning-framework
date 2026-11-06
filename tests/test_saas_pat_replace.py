"""One active MCP PAT per workspace — replace requires explicit flag."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_pat_mint_requires_replace_when_active():
    from mymlfw.saas.db.pat_data import PatExistsError
    from mymlfw.saas.pats import PatStore

    store = PatStore()
    first = store.create(workspace_id="org_01HPATTEST000000000000000")
    assert first.token.startswith("mlp_")

    with pytest.raises(PatExistsError):
        await store.acreate(workspace_id="org_01HPATTEST000000000000000")

    second = await store.acreate(
        workspace_id="org_01HPATTEST000000000000000", replace=True
    )
    assert second.token != first.token
    assert store.verify(first.token) is None
    assert store.verify(second.token) is not None
