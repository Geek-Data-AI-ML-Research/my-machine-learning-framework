"""DS playbook catalogs: modality strategy ladders and paradigm shifts.

Shared by the CLI (``python -m mymlfw playbook …``) and Campaign SaaS Studio
(``GET /v1/playbook/catalog``). Never start a campaign with a heavy model —
Stages 1–3 (EDA → CV lock → dumb baseline) come first.
"""

from __future__ import annotations

from typing import Any, Literal

Modality = Literal["tabular", "text", "vision", "sequential"]
VenueKind = Literal["kaggle", "standalone"]
Tier = Literal["default", "escalate", "paradigm"]

MODALITIES: tuple[Modality, ...] = ("tabular", "text", "vision", "sequential")
VENUE_KINDS: tuple[VenueKind, ...] = ("kaggle", "standalone")

_STRATEGY_CATALOG: dict[str, list[dict[str, str]]] = {
    "tabular": [
        {
            "id": "tab_trees",
            "tier": "default",
            "title": "Gradient boosted trees + linear",
            "detail": (
                "LightGBM / XGBoost / CatBoost + Ridge/Logistic on raw + engineered "
                "features. Start and often finish here."
            ),
        },
        {
            "id": "tab_stack",
            "tier": "escalate",
            "title": "Diverse tree/linear ensemble + residual stack",
            "detail": (
                "Orthogonal OOF stacking / hillclimb after a single strong tree "
                "plateaus (Kaggle squeeze path)."
            ),
        },
        {
            "id": "tab_mlp",
            "tier": "escalate",
            "title": "FT-Transformer / deep MLP",
            "detail": (
                "Only after trees plateau on locked CV — high capacity, easy to "
                "overfit on small tabular."
            ),
        },
        {
            "id": "tab_gpt2",
            "tier": "paradigm",
            "title": "GPT-2 / small LM on tokenized rows",
            "detail": (
                "Viable when the table is synthetic-from-NN (many Playground seasons). "
                "Not a commercial default."
            ),
        },
        {
            "id": "tab_tabpfn",
            "tier": "paradigm",
            "title": "TabPFN / prior-fitted networks",
            "detail": (
                "Strong on small-n, many-column tables; watch license, row limits, "
                "and latency."
            ),
        },
    ],
    "text": [
        {
            "id": "txt_linear",
            "tier": "default",
            "title": "TF-IDF / bag-of-words + Logistic",
            "detail": "Fast CPU baseline; establishes a bar before any transformer spend.",
        },
        {
            "id": "txt_embed",
            "tier": "default",
            "title": "Frozen sentence embeddings + linear",
            "detail": "Open embeddings or API vectors → Logistic/Ridge; cheap semantic lift.",
        },
        {
            "id": "txt_deberta",
            "tier": "escalate",
            "title": "DeBERTa / RoBERTa fine-tune",
            "detail": (
                "Best default when real human text carries the label "
                "(tickets, chats, code)."
            ),
        },
        {
            "id": "txt_llm",
            "tier": "escalate",
            "title": "Open-weight LLM / API few-shot",
            "detail": (
                "Long context, reasoning, or weak labels — after linear + encoder "
                "baselines exist."
            ),
        },
    ],
    "vision": [
        {
            "id": "vis_frozen",
            "tier": "default",
            "title": "Frozen ConvNeXt / ViT + linear or LightGBM head",
            "detail": "Extract embeddings once; train a cheap head before any fine-tune.",
        },
        {
            "id": "vis_ft",
            "tier": "escalate",
            "title": "Fine-tune backbone",
            "detail": "When frozen features plateau and you have enough labeled images.",
        },
        {
            "id": "vis_det",
            "tier": "escalate",
            "title": "Detection / segmentation (YOLO, Mask R-CNN family)",
            "detail": "When the task is localize-or-mask, not global classify.",
        },
        {
            "id": "vis_multi",
            "tier": "paradigm",
            "title": "Multimodal late fusion (image + tabular)",
            "detail": (
                "Unimodal baselines first; fuse only if each stream beats chance alone."
            ),
        },
    ],
    "sequential": [
        {
            "id": "seq_roll",
            "tier": "default",
            "title": "Rolling-window aggregates + trees",
            "detail": "count_last_24h, mean_last_7d, recency — usually wins before RNNs.",
        },
        {
            "id": "seq_gru",
            "tier": "escalate",
            "title": "GRU / LSTM on event sequences",
            "detail": (
                "When order matters beyond aggregates and you have millions of sequences."
            ),
        },
        {
            "id": "seq_tfm",
            "tier": "escalate",
            "title": "Lightweight sequence Transformer",
            "detail": (
                "Long-range dependence; keep context windows and latency budgets honest."
            ),
        },
        {
            "id": "seq_surv",
            "tier": "paradigm",
            "title": "Survival / Hawkes / point-process",
            "detail": (
                "When the target is time-to-event or self-exciting arrivals, not a flat "
                "row label."
            ),
        },
    ],
}

_PARADIGM_SHIFTS: list[dict[str, Any]] = [
    {
        "id": "synth_gpt_tabular",
        "title": "Synthetic NN tabular → GPT-2 / token LM",
        "detail": (
            "Train rows likely generated by a neural process (Playground-style). "
            "Tokenize rows; small LM can beat trees after Stage 3."
        ),
        "when": "tabular",
        "venues": ["kaggle", "standalone"],
    },
    {
        "id": "text_dominates",
        "title": "Text column dominates → encoder / LLM path",
        "detail": (
            "A free-text field carries most signal. After TF-IDF linear, escalate to "
            "DeBERTa / embeddings — not more tree depth on bag features alone."
        ),
        "when": "text",
        "venues": ["kaggle", "standalone"],
    },
    {
        "id": "small_n_tabpfn",
        "title": "Small-n high-p → TabPFN / strong priors",
        "detail": (
            "Hundreds–few thousand rows, wide feature space. Prior-fitted nets can "
            "leapfrog underfit trees."
        ),
        "when": "tabular",
        "venues": ["kaggle", "standalone"],
    },
    {
        "id": "label_delay",
        "title": "Label delay / chargeback lag",
        "detail": (
            "Positive labels arrive days–weeks late. Time-aware CV and delayed-label "
            "simulation beat any model upgrade."
        ),
        "when": "any",
        "venues": ["standalone"],
    },
    {
        "id": "entity_leak",
        "title": "Entity leakage → Group / purge CV",
        "detail": (
            "Same customer/device in train and valid. Switch to GroupKFold / purged "
            "time splits before more features."
        ),
        "when": "any",
        "venues": ["kaggle", "standalone"],
    },
    {
        "id": "cost_sensitive",
        "title": "Cost-sensitive thresholding",
        "detail": (
            "Business $FN/$FP asymmetry. Calibrate and set dollar thresholds before "
            "chasing 0.001 AUC with ensembles."
        ),
        "when": "any",
        "venues": ["standalone"],
    },
    {
        "id": "multimodal_fusion",
        "title": "Multimodal late fusion",
        "detail": (
            "Image/text + tabular. Fuse only after each modality has its own Stage 3 "
            "baseline."
        ),
        "when": "any",
        "venues": ["kaggle", "standalone"],
    },
    {
        "id": "kaggle_bps",
        "title": "Kaggle last 0.1 bps squeeze",
        "detail": (
            "Diverse model zoo + residual stacking / multi-hour GPU polishers — only "
            "after Stages 1–4 are solid."
        ),
        "when": "any",
        "venues": ["kaggle"],
    },
    {
        "id": "commercial_stop",
        "title": "Commercial stop rule (1–2 models)",
        "detail": (
            "Latency <20ms, maintainability, explainability. Refuse GPT polishers; "
            "ship calibrated LightGBM/CatBoost."
        ),
        "when": "any",
        "venues": ["standalone"],
    },
    {
        "id": "vision_detection",
        "title": "Detection / localization task",
        "detail": (
            "Boxes or masks required. Classification backbones are the wrong ladder — "
            "use detection heads early after a frozen embed baseline."
        ),
        "when": "vision",
        "venues": ["kaggle", "standalone"],
    },
]


def modality_strategies(modality: str) -> list[dict[str, str]]:
    """Return the ordered strategy ladder for a training-data modality."""
    key = (modality or "tabular").strip().lower()
    if key not in _STRATEGY_CATALOG:
        raise ValueError(
            f"unknown modality {modality!r}; choose one of {', '.join(MODALITIES)}"
        )
    return [dict(row) for row in _STRATEGY_CATALOG[key]]


def paradigm_shifts(
    *, modality: str = "tabular", kind: str = "standalone"
) -> list[dict[str, Any]]:
    """Return paradigm shifts filtered by venue kind and data modality."""
    venue = (kind or "standalone").strip().lower()
    if venue not in VENUE_KINDS:
        raise ValueError(
            f"unknown kind {kind!r}; choose one of {', '.join(VENUE_KINDS)}"
        )
    mod = (modality or "tabular").strip().lower()
    if mod not in MODALITIES:
        raise ValueError(
            f"unknown modality {modality!r}; choose one of {', '.join(MODALITIES)}"
        )
    out: list[dict[str, Any]] = []
    for row in _PARADIGM_SHIFTS:
        venues = row.get("venues") or []
        if venue not in venues:
            continue
        when = row.get("when") or "any"
        if when != "any" and when != mod:
            continue
        out.append(
            {
                "id": row["id"],
                "title": row["title"],
                "detail": row["detail"],
                "when": when,
                "venues": list(venues),
            }
        )
    return out


def playbook_catalog(
    *, modality: str = "tabular", kind: str = "standalone"
) -> dict[str, Any]:
    """Filtered catalog payload for CLI JSON / Studio GET."""
    mod = (modality or "tabular").strip().lower()
    venue = (kind or "standalone").strip().lower()
    return {
        "modality": mod,
        "kind": venue,
        "strategies": modality_strategies(mod),
        "paradigm_shifts": paradigm_shifts(modality=mod, kind=venue),
        "modalities": list(MODALITIES),
        "kinds": list(VENUE_KINDS),
        "order": [
            "eda",
            "validation",
            "dumb_baseline",
            "domain_features",
            "path_split",
            "optional_paradigm_shifts",
        ],
        "strategies_by_modality": {
            m: modality_strategies(m) for m in MODALITIES
        },
        "all_paradigm_shifts": [
            {
                "id": row["id"],
                "title": row["title"],
                "detail": row["detail"],
                "when": row["when"],
                "venues": list(row["venues"]),
            }
            for row in _PARADIGM_SHIFTS
        ],
    }


def build_seed_roadmap(
    *,
    modality: str = "tabular",
    kind: str = "standalone",
    baseline: str = "lightgbm",
    validation: str = "skf5",
    shifts: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Roadmap strategy docs (title/plan/priority) matching the Studio wizard seed."""
    is_kaggle = (kind or "").strip().lower() == "kaggle"
    mod = (modality or "tabular").strip().lower()
    ladder = modality_strategies(mod)
    ladder_text = "\n".join(
        f"• [{s['tier']}] {s['title']} — {s['detail']}" for s in ladder
    )
    modality_label = {
        "tabular": "Structured tabular",
        "text": "Text / documents",
        "vision": "Images / video / audio",
        "sequential": "Sequential events",
    }.get(mod, mod)
    validation_label = {
        "skf5": "5-fold StratifiedKFold",
        "time_group": "Time holdout + group split",
        "group_kfold": "GroupKFold (entity-safe)",
    }.get(validation, validation)
    baseline_label = {
        "lightgbm": "LightGBM (default trees)",
        "logistic": "Logistic / Ridge",
        "xgboost": "XGBoost",
        "catboost": "CatBoost",
    }.get(baseline, baseline)

    if mod == "text":
        baseline_plan = (
            f"After EDA + CV lock: start with a fast linear/logistic or embedding + "
            f"linear baseline before heavy LLMs. Preferred starter: {baseline_label}. "
            "Only escalate to DeBERTa / open-weight LLMs if text columns carry the signal."
        )
    elif mod == "vision":
        baseline_plan = (
            "After EDA + CV lock: extract pretrained backbone embeddings "
            f"(ConvNeXt / ViT) and train a linear/LightGBM head before fine-tuning. "
            f"Starter track: {baseline_label} on frozen features."
        )
    elif mod == "sequential":
        baseline_plan = (
            "After EDA + CV lock: build rolling-window aggregates "
            f"(count_last_24h, mean_last_7d) and beat them with {baseline_label}. "
            "Only then test a small GRU / lightweight Transformer if volume justifies it."
        )
    else:
        baseline_plan = (
            f"Run out-of-the-box {baseline_label} on raw features (CPU, ~15–60s). "
            "Record OOF score + feature importances. A single column with ~0.99 "
            "importance is a leakage alarm — stop and fix CV/features."
        )

    items: list[dict[str, Any]] = [
        {
            "title": "Stage 1 — EDA & data hygiene",
            "priority": 10,
            "plan": (
                "Inspect shape, dtypes, target rate, missingness, outliers, and "
                "corrupted timestamps before any model code.\n"
                f"Venue: {'Kaggle competition' if is_kaggle else 'Commercial / standalone'}.\n"
                f"Modality: {modality_label}.\n"
                + (
                    "Confirm train/test schema parity and synthetic quirks."
                    if is_kaggle
                    else "Also audit how the label was created (e.g. chargeback lag)."
                )
            ),
        },
        {
            "title": "Stage 2 — Lock leak-free validation",
            "priority": 20,
            "plan": (
                f"Chosen split: {validation_label}.\n"
                "Do not change folds/random_state casually after this stage.\n"
                + (
                    "Use stratified folds so each fold mirrors the target rate."
                    if is_kaggle
                    else "Prefer time-based holdout plus group integrity."
                )
            ),
        },
        {
            "title": "Stage 3 — 60-second dumb baseline",
            "priority": 30,
            "plan": baseline_plan,
        },
        {
            "title": "Stage 4 — Domain feature engineering",
            "priority": 40,
            "plan": (
                "Create ratios, velocities, historical rates (OOF target encoding), "
                "and interactions. Keep a feature only if it beats Stage 3 on the "
                "locked validation split."
            ),
        },
        {
            "title": (
                "Stage 5 — Kaggle squeeze path (final 40%)"
                if is_kaggle
                else "Stage 5 — Commercial deploy path (final 40%)"
            ),
            "priority": 50,
            "plan": (
                (
                    "Primary goal: squeeze every 0.1 bps on a static test file.\n"
                    "Expect diverse ensembles after Stages 1–4 are solid.\n"
                    "Use LLMs/GPT on numeric columns only when data is synthetic-from-NN."
                    if is_kaggle
                    else "Primary goal: reliable ROI, fast inference, maintainability.\n"
                    "Prefer 1–2 fast calibrated models. LLMs only for real human text."
                )
                + f"\n\nModality strategy ladder ({modality_label}):\n{ladder_text}"
            ),
        },
    ]

    wanted = set(shifts or [])
    available = {s["id"]: s for s in paradigm_shifts(modality=mod, kind=kind)}
    for i, sid in enumerate(s for s in (shifts or []) if s in available):
        s = available[sid]
        items.append(
            {
                "title": f"Paradigm shift — {s['title']}",
                "priority": 60 + i * 10,
                "plan": (
                    f"{s['detail']}\n\nGate: only after Stages 1–3 are executed on "
                    f"locked CV. If it fails Stage-3 beat, mark dead-end and return "
                    f"to the default ladder.\nModality context: {modality_label}."
                ),
            }
        )
    unused = wanted - set(available)
    if unused:
        raise ValueError(
            "unknown or inapplicable paradigm shift id(s): " + ", ".join(sorted(unused))
        )
    return items
