"""3-bucket Project Brain retrieval (A promoted, B dead_ends, C kaggle intel)."""

from __future__ import annotations

import re
from typing import Any, Literal

from mymlfw.saas.rag.rescore import rescore_hits
from mymlfw.saas.rag.rrf import rrf_fuse
from mymlfw.saas.schemas import BrainHit

Scope = Literal["dead_ends", "episodes", "kaggle_intel", "all"]


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9_]{2,}", (text or "").lower()) if t}


def _lexical_score(query: str, body: str) -> float:
    q = _tokenize(query)
    if not q:
        return 0.0
    b = _tokenize(body)
    if not b:
        return 0.0
    hit = len(q & b)
    return hit / max(1, len(q))


def _vectorish_score(query: str, body: str) -> float:
    """Cheap cosine-of-hash-tokens proxy (no external embed required for gather)."""
    from mymlfw.saas.llm import _hash_embed

    a = _hash_embed(query)
    b = _hash_embed(body[:2000])
    return sum(x * y for x, y in zip(a, b, strict=True))


def gather_corpus(
    *,
    experiments: list[dict[str, Any]],
    dead_ends: list[dict[str, Any]],
    episode_cards: list[dict[str, Any]],
    kaggle_intel: list[dict[str, Any]] | None = None,
    axioms: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for exp in experiments:
        if exp.get("deleted_at"):
            continue
        verdict = str(exp.get("verdict") or "")
        if verdict == "kill":
            continue
        text = (
            f"{exp.get('variable') or ''} {exp.get('title') or ''} "
            f"cv={exp.get('cv_mean')} delta={exp.get('cv_delta')} verdict={verdict}"
        )
        rows.append(
            {
                "doc_id": exp.get("_id") or exp.get("id"),
                "doc_type": "promoted",
                "text": text.strip(),
                "epoch_id": exp.get("epoch_id"),
                "utility_weight": float(exp.get("utility_weight") or 1.0),
                "snr_weight": 1.5 if float(exp.get("cv_delta") or 0) > 0 else 1.0,
                "cv_mean": exp.get("cv_mean"),
                "verdict": verdict,
            }
        )
    for ded in dead_ends:
        if ded.get("deleted_at"):
            continue
        text = f"{ded.get('variable') or ''} {ded.get('lesson') or ''}"
        rows.append(
            {
                "doc_id": ded.get("_id") or ded.get("id"),
                "doc_type": "dead_end",
                "text": text.strip(),
                "epoch_id": ded.get("epoch_id"),
                "utility_weight": float(ded.get("utility_weight") or 1.0),
                "snr_weight": float(ded.get("snr_weight") or 1.2),
                "status": ded.get("status"),
            }
        )
    for card in episode_cards:
        if card.get("deleted_at") or card.get("falsified_on_cv"):
            continue
        rows.append(
            {
                "doc_id": card.get("_id") or card.get("id"),
                "doc_type": "episode",
                "text": str(card.get("semantic_summary") or ""),
                "epoch_id": card.get("epoch_id"),
                "utility_weight": float(card.get("utility_weight") or 1.0),
                "snr_weight": float(card.get("snr_weight") or 1.0),
            }
        )
    for row in kaggle_intel or []:
        rows.append(
            {
                "doc_id": row.get("_id") or row.get("id") or f"mem_kaggle_{len(rows)}",
                "doc_type": "kaggle_intel",
                "text": str(row.get("text") or row.get("summary") or ""),
                "epoch_id": row.get("epoch_id"),
                "utility_weight": float(row.get("utility_weight") or 0.9),
                "snr_weight": 0.8,
            }
        )
    for ax in axioms or []:
        if not ax.get("pinned") and not ax.get("statement"):
            continue
        rows.append(
            {
                "doc_id": ax.get("_id") or ax.get("id"),
                "doc_type": "axiom",
                "text": str(ax.get("statement") or ""),
                "epoch_id": ax.get("epoch_id"),
                "utility_weight": 1.2,
                "snr_weight": 1.5,
            }
        )
    return [r for r in rows if r.get("doc_id") and r.get("text")]


def retrieve_three_buckets(
    *,
    query: str,
    corpus: list[dict[str, Any]],
    current_epoch: str | None,
    scope: Scope = "all",
    max_tokens: int = 512,
) -> dict[str, list[BrainHit]]:
    """Return buckets A/B/C with caps 4/4/3 after RRF+rescore."""
    filtered = corpus
    if scope == "dead_ends":
        filtered = [r for r in corpus if r["doc_type"] == "dead_end"]
    elif scope == "episodes":
        filtered = [r for r in corpus if r["doc_type"] in {"episode", "promoted"}]
    elif scope == "kaggle_intel":
        filtered = [r for r in corpus if r["doc_type"] == "kaggle_intel"]

    lexical = sorted(
        (
            {**r, "lex": _lexical_score(query, r["text"])}
            for r in filtered
        ),
        key=lambda r: (-float(r["lex"]), str(r["doc_id"])),
    )
    lexical = [r for r in lexical if float(r["lex"]) > 0] or lexical[:8]
    vectorial = sorted(
        (
            {**r, "vec": _vectorish_score(query, r["text"])}
            for r in filtered
        ),
        key=lambda r: (-float(r["vec"]), str(r["doc_id"])),
    )
    fused = rrf_fuse(lexical, vectorial)
    scored = rescore_hits(fused, current_epoch=current_epoch)

    bucket_a = [r for r in scored if r["doc_type"] in {"promoted", "axiom"}][:4]
    bucket_b = [r for r in scored if r["doc_type"] == "dead_end"][:4]
    bucket_c = [r for r in scored if r["doc_type"] in {"kaggle_intel", "episode"}][:3]

    def _to_hits(rows: list[dict[str, Any]], bucket: str) -> list[BrainHit]:
        hits: list[BrainHit] = []
        budget = max_tokens
        for r in rows:
            text = str(r.get("text") or "")
            if len(text) > budget:
                text = text[: max(0, budget - 3)] + "..."
            budget -= len(text)
            hits.append(
                BrainHit(
                    doc_id=str(r["doc_id"]),
                    doc_type=r["doc_type"],  # type: ignore[arg-type]
                    bucket=bucket,  # type: ignore[arg-type]
                    text=text,
                    score=float(r.get("score") or 0.0),
                    epoch_id=r.get("epoch_id"),
                    utility_weight=float(r.get("utility_weight") or 1.0),
                )
            )
            if budget <= 0:
                break
        return hits

    return {
        "A": _to_hits(bucket_a, "A"),
        "B": _to_hits(bucket_b, "B"),
        "C": _to_hits(bucket_c, "C"),
    }
