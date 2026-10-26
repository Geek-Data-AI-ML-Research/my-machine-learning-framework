"""Average adapter tensors in weight space."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from mymlfw.errors import MymlfwError


def soup_adapters(paths, weights, out_dir) -> Path:
    from safetensors.numpy import load_file, save_file

    weights = np.asarray(weights, dtype=float)
    if abs(float(weights.sum()) - 1.0) > 1e-6:
        raise MymlfwError("SOUP_WEIGHTS", "Soup weights must sum to 1.", weights=weights.tolist())
    accumulator = None
    keys = None
    for path, weight in zip(paths, weights):
        tensors = load_file(str(path))
        current = set(tensors)
        if keys is None:
            keys = current
            accumulator = {name: float(weight) * value for name, value in tensors.items()}
            continue
        if current != keys:
            raise MymlfwError(
                "SOUP_KEY_MISMATCH",
                "Every adapter must contain the same tensor names.",
                missing=sorted(keys.symmetric_difference(current)),
            )
        for name in keys:
            accumulator[name] = accumulator[name] + float(weight) * tensors[name]
    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=True)
    out_path = destination / "adapter_model.safetensors"
    save_file(accumulator, str(out_path))
    return out_path
