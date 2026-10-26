"""PEFT config guards and a dry-run that does not load weights."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from mymlfw.campaign.ledger import register_probe
from mymlfw.errors import MymlfwError


def validate_peft_config(cfg: dict) -> dict:
    peft_type = str(cfg.get("peft_type", "")).lower()
    if peft_type not in {"dora", "lora"}:
        raise MymlfwError("BAD_PEFT", "peft_type must be dora or lora.", peft_type=peft_type)
    rank = int(cfg.get("rank", 0))
    alpha = int(cfg.get("lora_alpha", 2 * rank))
    targets = cfg.get("target_modules") or []
    if not targets:
        raise MymlfwError("MISSING_TARGETS", "target_modules is required.", note="attn and MLP targets")
    warnings = []
    if alpha != 2 * rank:
        warnings.append(f"lora_alpha={alpha} != 2*rank={2 * rank}")
    return {
        "lora_alpha": alpha,
        "peft_type": peft_type,
        "rank": rank,
        "target_modules": list(targets),
        "warnings": warnings,
    }


def lora_dry_run(
    train_csv,
    ledger,
    *,
    experiment_id: str,
    baseline_id: str,
    variable: str,
    expected_band_low: float,
    expected_band_high: float,
    note: str = "",
    soft_targets: str | None = None,
    kl_alpha: float = 0.5,
    out_dir=None,
    config=None,
) -> dict:
    peft_report = None
    if config is not None:
        loaded = config if isinstance(config, dict) else yaml.safe_load(Path(config).read_text())
        peft_report = validate_peft_config(loaded)
    frame = pd.read_csv(train_csv)
    required = {"text", "label"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise MymlfwError("BAD_COLUMNS", "The training frame needs text and label columns.", missing=missing)
    if soft_targets is not None and not 0.0 <= float(kl_alpha) <= 1.0:
        raise MymlfwError("BAD_KL_ALPHA", "kl_alpha must lie in [0, 1].", kl_alpha=kl_alpha)
    register_probe(
        ledger,
        experiment_id=experiment_id,
        baseline_id=baseline_id,
        variable=variable,
        change_count=1,
        expected_band_low=expected_band_low,
        expected_band_high=expected_band_high,
        note=note,
    )
    report = {
        "columns": list(frame.columns),
        "dry_run": True,
        "kl_alpha": float(kl_alpha) if soft_targets else None,
        "model_loaded": False,
        "peft": peft_report,
        "rows": int(len(frame)),
        "soft_targets": soft_targets,
    }
    if out_dir is not None:
        destination = Path(out_dir)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "dry_run.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    return report


def smoke_backward() -> dict:
    """One CPU backward on a tiny config. Imports torch only when called."""
    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import BertConfig, AutoModel

    config = BertConfig(
        hidden_size=32,
        intermediate_size=64,
        num_attention_heads=4,
        num_hidden_layers=2,
        vocab_size=100,
    )
    model = AutoModel.from_config(config)
    peft_config = LoraConfig(r=4, lora_alpha=8, target_modules=["query", "value"], bias="none")
    model = get_peft_model(model, peft_config)
    model.train()
    batch = torch.ones(2, 8, dtype=torch.long)
    outputs = model(input_ids=batch)
    loss = outputs.last_hidden_state.float().pow(2).mean()
    loss.backward()
    return {"loss": float(loss.detach().cpu()), "device": "cpu"}
