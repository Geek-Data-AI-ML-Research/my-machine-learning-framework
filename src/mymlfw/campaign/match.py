"""Match a data profile to recipe cards.

The rules are deterministic:

- A card that sets ``n_classes_min`` is dropped when the profile has fewer classes.
- ``target_type: multiclass`` matches when the target has more than 2 classes.
- ``target_type: binary`` matches when the target has exactly 2 classes.
- ``target_type: ranking`` matches when an id column exists and there is no label.
- Any other ``target_type``, including a missing one, stays eligible.
- When a text column exists, cards with ``has_text_col`` score higher.
- When a group candidate exists, cards with ``has_group_col`` score higher.
- An exact target-type match adds a smaller bonus.
- Cards with a positive score are returned, highest first, at most two.
- Equal scores break by recipe id ascending.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from mymlfw.paths import repo_root


def load_recipe_cards(root: Path | None = None) -> list[dict]:
    recipes = (root or repo_root()) / "recipes"
    if not recipes.is_dir():
        return []
    cards = []
    for path in sorted(recipes.glob("*.yaml")):
        loaded = yaml.safe_load(path.read_text())
        if isinstance(loaded, dict) and loaded.get("id"):
            cards.append(loaded)
    return cards


def _target_match(target_type, features: dict):
    if not target_type:
        return None
    n_classes = features.get("n_classes")
    if target_type == "multiclass":
        return n_classes is not None and int(n_classes) > 2
    if target_type == "binary":
        return n_classes is not None and int(n_classes) == 2
    if target_type == "ranking":
        return (not features.get("has_label")) and bool(features.get("has_id_col"))
    return None


def _score(card: dict, features: dict):
    signatures = card.get("signatures") or {}
    minimum = signatures.get("n_classes_min")
    n_classes = features.get("n_classes")
    if minimum is not None and (n_classes is None or int(n_classes) < int(minimum)):
        return None
    matched = _target_match(signatures.get("target_type"), features)
    if matched is False:
        return None
    score = 0
    if features.get("has_text_col") and signatures.get("has_text_col"):
        score += 2
    if features.get("has_group_col") and signatures.get("has_group_col"):
        score += 2
    if matched is True:
        score += 1
    if score <= 0:
        return None
    return score


def recommend_recipes(profile_features: dict, cards: list[dict] | None = None) -> list[dict]:
    """Return up to two recipe cards for ``profile_features``.

    See the module docstring for the match order. ``profile_features`` uses
    ``has_text_col``, ``has_group_col``, ``n_classes``, ``has_label``, and
    ``has_id_col``.
    """

    chosen = load_recipe_cards() if cards is None else cards
    ranked = []
    for card in chosen:
        score = _score(card, profile_features)
        if score is None:
            continue
        ranked.append((score, str(card.get("id", "")), card))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [card for _, _, card in ranked[:2]]
