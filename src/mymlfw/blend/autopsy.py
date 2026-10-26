"""OOF error slices an agent can read before the next probe."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from mymlfw.blend.bundle import as_log_probs, load_npz


def diagnose_oof(oof_path, train, out_path, label_col: str = "label", text_col: str = "text", group_col: str = "group") -> Path:
    bundle = load_npz(oof_path)
    frame = train if isinstance(train, pd.DataFrame) else pd.read_csv(train)
    frame = frame.copy()
    frame["id"] = frame["id"].astype(str)
    order = {row_id: index for index, row_id in enumerate(bundle.ids.tolist())}
    frame = frame[frame["id"].isin(order)].copy()
    frame["_row"] = frame["id"].map(order)
    frame = frame.sort_values("_row")
    logp = as_log_probs(bundle)[frame["_row"].to_numpy()]
    classes = bundle.classes
    class_index = {label: index for index, label in enumerate(classes.tolist())}
    truth = frame[label_col].astype(str).to_numpy()
    pred_idx = logp.argmax(axis=1)
    pred = classes[pred_idx]
    pairs = Counter()
    for gold, guess in zip(truth, pred):
        if gold != guess:
            pairs[(gold, guess)] += 1
    top_pairs = pairs.most_common(10)
    lengths = frame[text_col].astype(str).str.len().to_numpy() if text_col in frame.columns else np.ones(len(frame))
    quartiles = np.quantile(lengths, [0.25, 0.5, 0.75]) if len(frame) else [0, 0, 0]
    bins = np.digitize(lengths, quartiles, right=True)
    length_lines = []
    for bucket in range(4):
        mask = bins == bucket
        acc = float(np.mean(pred[mask] == truth[mask])) if np.any(mask) else float("nan")
        length_lines.append(f"q{bucket} n={int(mask.sum())} accuracy={acc:.4g}")
    group_lines = []
    if group_col in frame.columns:
        sizes = frame.groupby(group_col)["id"].transform("size").to_numpy()
        for label, mask in (
            ("size_1", sizes == 1),
            ("size_2_to_4", (sizes >= 2) & (sizes <= 4)),
            ("size_5_plus", sizes >= 5),
        ):
            acc = float(np.mean(pred[mask] == truth[mask])) if np.any(mask) else float("nan")
            group_lines.append(f"{label} n={int(mask.sum())} accuracy={acc:.4g}")
    losses = []
    for row_i, gold in enumerate(truth):
        if gold == pred[row_i] or gold not in class_index:
            continue
        loss = float(-logp[row_i, class_index[gold]])
        losses.append((loss, frame["id"].iloc[row_i], gold, pred[row_i]))
    losses.sort(reverse=True)
    worst = losses[:20]
    pair_text = "\n".join(f"{gold}->{guess} {count}" for (gold, guess), count in top_pairs) or "none"
    worst_text = "\n".join(f"{row_id} loss={loss:.4g} gold={gold} pred={guess}" for loss, row_id, gold, guess in worst) or "none"
    text = (
        "# ERROR_AUTOPSY\n\n"
        f"## confusion\n{pair_text}\n\n"
        f"## length_quartile\n" + "\n".join(length_lines) + "\n\n"
        f"## group_size\n" + ("\n".join(group_lines) or "none") + "\n\n"
        f"## highest_loss\n{worst_text}\n"
    )
    out_path = Path(out_path)
    out_path.write_text(text)
    return out_path
