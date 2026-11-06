"""Tier2 archetype playbook cold-start weighted into Tier1 project memory."""

from __future__ import annotations

from typing import Any


def dataset_fingerprint(meta: dict[str, Any] | None) -> str:
    """Bucketed fingerprint: task_type / size / cat / skew / metric / adv regime."""
    m = meta or {}
    task = str(m.get("task_type") or m.get("task") or "unknown")
    n_rows = int(m.get("n_rows") or 0)
    n_feat = int(m.get("n_features") or m.get("n_cols") or 0)
    rows_bucket = (
        "xs" if n_rows < 1_000 else "s" if n_rows < 10_000 else "m" if n_rows < 100_000 else "l"
    )
    feat_bucket = "f_xs" if n_feat < 20 else "f_s" if n_feat < 100 else "f_m" if n_feat < 500 else "f_l"
    cat_ratio = float(m.get("cat_ratio") or 0.0)
    cat_bucket = "cat_lo" if cat_ratio < 0.2 else "cat_mid" if cat_ratio < 0.6 else "cat_hi"
    skew = float(m.get("target_skew") or m.get("skew") or 0.0)
    skew_bucket = "skew_lo" if abs(skew) < 1.0 else "skew_hi"
    metric = str(m.get("metric") or "unknown")
    adv = float(m.get("adv_auc") or 0.5)
    adv_bucket = "adv_ok" if adv < 0.6 else "adv_warn" if adv < 0.75 else "adv_leak"
    return f"{task}|{rows_bucket}|{feat_bucket}|{cat_bucket}|{skew_bucket}|{metric}|{adv_bucket}"


def tier2_weight(*, experiment_count: int) -> float:
    """Weight Tier2→Tier1 as experiments grow past ~5 (→0)."""
    if experiment_count <= 0:
        return 1.0
    if experiment_count >= 12:
        return 0.0
    if experiment_count <= 5:
        return max(0.25, 1.0 - 0.1 * experiment_count)
    return max(0.0, 0.5 - 0.08 * (experiment_count - 5))


def default_archetype_playbook(fingerprint: str) -> list[dict[str, Any]]:
    """Global archetype cards keyed by fingerprint (in-process catalog)."""
    base = fingerprint.split("|")[0] if fingerprint else "unknown"
    templates = [
        {
            "_id": f"mem_archetype_{base}_fold0",
            "id": f"mem_archetype_{base}_fold0",
            "text": (
                f"Archetype[{fingerprint}]: start with fold0_smoke after any "
                "dead end; keep one-variable levers."
            ),
            "doc_type": "kaggle_intel",
            "utility_weight": 0.85,
            "snr_weight": 0.8,
            "tier": 2,
            "fingerprint": fingerprint,
        },
        {
            "_id": f"mem_archetype_{base}_snr",
            "id": f"mem_archetype_{base}_snr",
            "text": (
                f"Archetype[{fingerprint}]: prefer high-SNR promotes; "
                "penalize same-epoch dead-end repeats."
            ),
            "doc_type": "kaggle_intel",
            "utility_weight": 0.85,
            "snr_weight": 0.8,
            "tier": 2,
            "fingerprint": fingerprint,
        },
    ]
    return templates


def blend_tier2_into_corpus(
    corpus: list[dict[str, Any]],
    *,
    fingerprint: str | None,
    experiment_count: int,
    playbook: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Append Tier2 rows scaled by ``tier2_weight`` into utility."""
    w = tier2_weight(experiment_count=experiment_count)
    if w <= 0 or not fingerprint:
        return corpus
    rows = list(corpus)
    for card in playbook or default_archetype_playbook(fingerprint):
        rows.append(
            {
                "doc_id": card.get("_id") or card.get("id"),
                "doc_type": card.get("doc_type") or "kaggle_intel",
                "text": str(card.get("text") or card.get("summary") or ""),
                "epoch_id": card.get("epoch_id"),
                "utility_weight": float(card.get("utility_weight") or 0.85) * w,
                "snr_weight": float(card.get("snr_weight") or 0.8),
                "tier": 2,
            }
        )
    return [r for r in rows if r.get("doc_id") and r.get("text")]
