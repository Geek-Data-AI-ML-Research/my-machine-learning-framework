"""Engine protocol. Predictors cross this boundary as objects or npz files."""

from __future__ import annotations

from typing import Protocol

from mymlfw.blend.bundle import PredictionBundle


class PredictorProtocol(Protocol):
    def predict(self, frame) -> PredictionBundle: ...
