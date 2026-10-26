"""Prediction bundles stored as ids, classes, values, and kind."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import log_softmax

from mymlfw.errors import AlignmentError, MymlfwError

KINDS = {"logits", "log_probs", "scores"}


@dataclass(frozen=True)
class PredictionBundle:
    ids: np.ndarray
    classes: np.ndarray
    values: np.ndarray
    kind: str
    name: str = ""

    def __post_init__(self):
        ids = np.asarray(self.ids).astype(str)
        classes = np.asarray(self.classes).astype(str)
        values = np.asarray(self.values, dtype=float)
        if self.kind not in KINDS:
            raise MymlfwError(
                "BAD_KIND",
                "kind must be logits, log_probs, or scores.",
                kind=self.kind,
            )
        if ids.shape[0] != values.shape[0]:
            raise MymlfwError("SHAPE", "ids and values disagree on rows.", name=self.name)
        if values.ndim != 2 or values.shape[1] != classes.shape[0]:
            raise MymlfwError("SHAPE", "values columns must match classes.", name=self.name)
        if len(ids) != len(set(ids.tolist())):
            raise AlignmentError("Ids must be unique.", file=self.name)
        object.__setattr__(self, "ids", ids)
        object.__setattr__(self, "classes", classes)
        object.__setattr__(self, "values", values)


def as_log_probs(bundle: PredictionBundle) -> np.ndarray:
    if bundle.kind == "log_probs":
        return np.array(bundle.values, copy=True)
    if bundle.kind == "logits":
        return log_softmax(bundle.values, axis=-1)
    return np.log(np.clip(bundle.values, 1e-7, 1.0))


def save_npz(path, bundle: PredictionBundle) -> None:
    np.savez(
        path,
        ids=bundle.ids,
        classes=bundle.classes,
        values=bundle.values,
        kind=np.array(bundle.kind),
        name=np.array(bundle.name),
    )


def load_npz(path, name: str = "") -> PredictionBundle:
    with np.load(path, allow_pickle=False) as saved:
        kind = saved["kind"]
        kind_s = str(kind.item() if getattr(kind, "shape", ()) == () else kind)
        stored = saved["name"] if "name" in saved.files else ""
        stored_s = str(stored.item() if getattr(stored, "shape", ()) == () else stored)
        return PredictionBundle(
            ids=saved["ids"],
            classes=saved["classes"],
            values=saved["values"],
            kind=kind_s,
            name=name or stored_s or str(path),
        )
