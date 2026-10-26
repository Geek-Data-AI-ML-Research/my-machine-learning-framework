"""Group-relative advantages. Tied rewards stay at zero and never divide."""

from __future__ import annotations

import numpy as np

from mymlfw.errors import MymlfwError


def reward(exec_r: float, syntax_r: float, heuristic_r: float, penalty_r: float) -> float:
    return float(exec_r) + float(syntax_r) + float(heuristic_r) - float(penalty_r)


def score_groups(rows) -> dict:
    """Turn reward components into group-relative advantages."""
    if len(rows) < 2:
        raise MymlfwError("GRPO_GROUP", "A GRPO group needs at least two sampled rewards.")
    rewards = [
        reward(row["exec"], row["syntax"], row["heuristic"], row["penalty"])
        for row in rows
    ]
    return {"rewards": rewards, "advantages": advantages(rewards).tolist()}


def advantages(rewards, eps: float = 1e-8) -> np.ndarray:
    values = np.asarray(rewards, dtype=float)
    if values.ndim != 1 or values.shape[0] < 2:
        raise ValueError("group_size must be >= 2")
    std = float(values.std())
    if std < 1e-8:
        return np.zeros_like(values)
    return (values - float(values.mean())) / (std + eps)
