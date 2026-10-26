"""Isolated branch workers and length-sorted inference order."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np

CELL2_TEMPLATE = '''import subprocess
import sys
from pathlib import Path

def length_order(lengths):
    order = lengths.argsort(kind="mergesort")
    return order

def run_worker(name):
    subprocess.run([sys.executable, f"{name}_worker.py"], check=True)
    return Path(f"preds_{name}.npz")
'''


def run_branch(worker, cwd) -> int:
    """Run a branch in a fresh interpreter so the parent does not keep its allocations."""
    completed = subprocess.run([sys.executable, str(worker)], cwd=str(cwd), check=True)
    return int(completed.returncode)


def length_sort(ids, lengths):
    ids = np.asarray(ids)
    lengths = np.asarray(lengths)
    order = np.argsort(lengths, kind="mergesort")
    restore = np.empty(len(order), dtype=int)
    restore[order] = np.arange(len(order))
    return ids[order], order, restore


def unsort(values, restore):
    return np.asarray(values)[restore]
