"""Structured project advise — always egresses through citation_firewall."""

from __future__ import annotations

from typing import Any

from mymlfw.saas.brain_store import CampaignBrainStore
from mymlfw.saas.llm import chat_completion
from mymlfw.saas.rag.audit import record_brain_event
from mymlfw.saas.rag.citation_firewall import enforce_citation_firewall
from mymlfw.saas.rag.cold_start import (
    blend_tier2_into_corpus,
    dataset_fingerprint,
)
from mymlfw.saas.rag.integrity import check_text_integrity, scrub_secrets
from mymlfw.saas.rag.query_expand import expand_query
from mymlfw.saas.rag.retrieve import gather_corpus, retrieve_three_buckets
from mymlfw.saas.schemas import (
    AdviseMissionDraft,
    AdviseResponse,
    BrainHit,
    QueryProjectBrainResponse,
)


def strategy_efficacy_lines(dead_ends: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for d in dead_ends[:8]:
        var = d.get("variable") or "?"
        lesson = (d.get("lesson") or "")[:120]
        w = float(d.get("utility_weight") or 1.0)
        lines.append(f"- {var} (utility={w:.2f}): {lesson}")
    return lines


def build_doc_index(
    *,
    goals: list[dict[str, Any]],
    experiments: list[dict[str, Any]],
    dead_ends: list[dict[str, Any]],
    episode_cards: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for g in goals:
        gid = str(g.get("_id") or g.get("id") or "")
        if gid:
            idx[gid] = {**g, "doc_type": "goal", "kind": "goal"}
    for e in experiments:
        eid = str(e.get("_id") or e.get("id") or "")
        if eid:
            idx[eid] = {**e, "doc_type": "experiment", "kind": "experiment"}
    for d in dead_ends:
        did = str(d.get("_id") or d.get("id") or "")
        if did:
            idx[did] = {**d, "doc_type": "dead_end", "kind": "dead_end"}
    for c in episode_cards:
        cid = str(c.get("_id") or c.get("id") or "")
        if cid:
            idx[cid] = {**c, "doc_type": "episode", "kind": "memory"}
    return idx


def query_project_brain_from_store(
    store: CampaignBrainStore,
    *,
    workspace_id: str,
    project_id: str,
    scope: str = "all",
    max_tokens: int = 512,
    query: str = "",
    error_slices: list[dict[str, Any] | str] | None = None,
) -> QueryProjectBrainResponse:
    proj = store.get_project(workspace_id, project_id)
    if proj is None:
        return QueryProjectBrainResponse(
            status="empty",
            message="project_not_found",
            results=[],
        )
    experiments = store.experiments.get(project_id, [])
    dead_ends = store.dead_ends.get(project_id, [])
    episodes = store.episode_cards.get(project_id, [])
    axioms = store.axioms.get(project_id, [])
    goals = store.goals.get(project_id, [])
    kaggle = getattr(store, "kaggle_intel", {}).get(project_id, [])
    corpus = gather_corpus(
        experiments=experiments,
        dead_ends=dead_ends,
        episode_cards=episodes,
        kaggle_intel=kaggle,
        axioms=axioms,
    )
    fp = dataset_fingerprint(proj.get("dataset_meta") or proj.get("fingerprint_meta"))
    corpus = blend_tier2_into_corpus(
        corpus,
        fingerprint=fp,
        experiment_count=len(experiments),
    )
    q = expand_query(
        query,
        error_slices=error_slices or proj.get("error_slices") or [],
        goal_titles=[str(g.get("title") or "") for g in goals],
    )
    buckets = retrieve_three_buckets(
        query=q,
        corpus=corpus,
        current_epoch=proj.get("epoch_id"),
        scope=scope if scope in {"dead_ends", "episodes", "kaggle_intel", "all"} else "all",  # type: ignore[arg-type]
        max_tokens=max_tokens,
    )
    flat: list[BrainHit] = [*buckets["A"], *buckets["B"], *buckets["C"]]
    return QueryProjectBrainResponse(
        status="ready" if flat else "empty",
        message="" if flat else "no_hits",
        results=flat,
        axioms=[str(a.get("statement") or "") for a in axioms if a.get("pinned")],
    )


def advise_project(
    store: CampaignBrainStore,
    *,
    workspace_id: str,
    project_id: str,
    task: str = "next experiment",
    max_missions: int = 3,
) -> AdviseResponse:
    proj = store.get_project(workspace_id, project_id)
    if proj is None:
        raise ValueError("project_not_found")
    goals = store.goals.get(project_id, [])
    experiments = store.experiments.get(project_id, [])
    dead_ends = store.dead_ends.get(project_id, [])
    episodes = store.episode_cards.get(project_id, [])
    axioms = store.axioms.get(project_id, [])
    efficacy = strategy_efficacy_lines(dead_ends)
    axiom_lines = [str(a.get("statement") or "") for a in axioms if a.get("pinned")]

    brain = query_project_brain_from_store(
        store,
        workspace_id=workspace_id,
        project_id=project_id,
        query=task,
        max_tokens=1024,
    )
    bucket_map = {"A": [], "B": [], "C": []}  # type: ignore[var-annotated]
    for hit in brain.results:
        bucket_map.setdefault(hit.bucket, []).append(hit)

    system = (
        "You are mymlfw Campaign advise. Cite only real IDs from context. "
        "Never invent ULIDs. Prefer dead-end lessons and promoted experiments.\n"
        "Strategy efficacy:\n" + "\n".join(efficacy[:6]) + "\n"
        "Axioms:\n" + "\n".join(axiom_lines[:5])
    )
    ctx_lines = [f"{h.doc_id} [{h.bucket}] {h.text}" for h in brain.results[:10]]
    user = f"Task: {task}\nContext:\n" + "\n".join(ctx_lines)
    chat = chat_completion(
        system=system,
        user=user,
        org_id=workspace_id,
        project_id=project_id,
        tool="advise",
    )
    integrity = check_text_integrity(chat.text)
    brief = scrub_secrets(chat.text) if not integrity.ok else chat.text

    primary_goal = next((g for g in goals if g.get("status") == "active"), None)
    goal_id = (primary_goal or {}).get("_id") or (primary_goal or {}).get("id")
    cited = [h.doc_id for h in brain.results[:3]]
    draft_missions = [
        {
            "title": f"Probe from brain: {task[:80]}",
            "goal_id": goal_id,
            "rationale_md": (
                f"Based on {', '.join(cited) if cited else 'project memory'}.\n\n{brief[:400]}"
            ),
            "cited_ids": cited,
        }
    ][:max_missions]

    # Optionally inject a hallucinated ID in local template path? Don't — firewall tested separately.
    index = build_doc_index(
        goals=goals,
        experiments=experiments,
        dead_ends=dead_ends,
        episode_cards=episodes,
    )

    def _fetch(ids: list[str]) -> dict[str, dict[str, Any]]:
        return {i: index[i] for i in ids if i in index}

    fw = enforce_citation_firewall(
        brief_md=brief,
        proposed_missions=draft_missions,
        fetch_docs=_fetch,
    )
    from mymlfw.saas.rag.utility import bump_times_cited

    bump_times_cited([*dead_ends, *episodes], fw.times_cited_incs)

    missions = [
        AdviseMissionDraft(
            title=str(m.get("title") or "probe"),
            goal_id=m.get("goal_id"),
            rationale_md=str(m.get("rationale_md") or ""),
            cited_ids=list(m.get("cited_ids") or []),
        )
        for m in fw.proposed_missions
    ]
    record_brain_event(
        "advise.completed",
        workspace_id=workspace_id,
        project_id=project_id,
        payload={
            "grounding_score": fw.grounding_score,
            "verified_ids": fw.verified_ids,
            "stripped_ids": fw.stripped_ids,
            "integrity_ok": integrity.ok,
        },
    )
    return AdviseResponse(
        project_id=project_id,
        brief_md=fw.brief_md,
        proposed_missions=missions,
        buckets=bucket_map,
        grounding_score=fw.grounding_score,
        strategy_efficacy=efficacy,
        axioms=axiom_lines,
        citation_firewall={
            "verified_ids": fw.verified_ids,
            "stripped_ids": fw.stripped_ids,
            "grounding_score": fw.grounding_score,
            "integrity_ok": integrity.ok,
            "integrity_reasons": list(integrity.reasons),
        },
    )
