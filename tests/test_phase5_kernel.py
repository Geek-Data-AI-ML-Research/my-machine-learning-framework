import ast
import json
import subprocess
import sys

import numpy as np
import pandas as pd

from mymlfw.errors import PayloadTooLargeError
from mymlfw.kernel import (
    build_notebook,
    extract_payload,
    length_sort,
    pack_deps,
    run_branch,
    simulate_test,
    unsort,
)


def _cells(src):
    src.mkdir()
    (src / "cell0_overview.md").write_text("# overview\n")
    (src / "cell1_stage.py").write_text("PAYLOAD = __PAYLOAD_B64__\nHASH = __PAYLOAD_SHA256__\n")
    (src / "cell2_run.py").write_text("import subprocess\nimport sys\nsubprocess.run([sys.executable, 'worker.py'])\n")
    (src / "cell3_fuse.py").write_text("print('fuse')\n")


def test_payload_round_trip_and_stable_hash(tmp_path):
    src = tmp_path / "src"
    _cells(src)
    (src / "a.py").write_text("print('a')\n")
    (src / "b.py").write_text("print('b')\n")
    first = tmp_path / "first.ipynb"
    second = tmp_path / "second.ipynb"
    build_notebook(src, first, ["a.py", "b.py"])
    build_notebook(src, second, ["a.py", "b.py"])
    assert first.read_bytes() == second.read_bytes()
    restored = extract_payload(first.with_suffix(".manifest.json"))
    assert restored["a.py"] == b"print('a')\n"
    assert restored["b.py"] == b"print('b')\n"
    notebook = json.loads(first.read_text())
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            ast.parse("".join(cell["source"]))


def test_kernel_build_cli_writes_the_notebook(tmp_path):
    src = tmp_path / "src"
    _cells(src)
    (src / "a.py").write_text("print('a')\n")
    out = tmp_path / "built.ipynb"
    completed = subprocess.run(
        [
            sys.executable, "-m", "mymlfw", "kernel", "build",
            "--src", str(src), "--out", str(out), "--payload", "a.py",
        ],
        check=False, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert out.is_file()
    assert "notebook_sha256" in json.loads(completed.stdout)


def test_large_payload_is_rejected(tmp_path):
    src = tmp_path / "src"
    _cells(src)
    (src / "big.py").write_text("x = " + repr("a" * 600_000) + "\n")
    out = tmp_path / "big.ipynb"
    try:
        build_notebook(src, out, ["big.py"])
    except PayloadTooLargeError as exc:
        assert exc.fields["nbytes"] > 512_000
    else:
        raise AssertionError("large payload was accepted")
    assert not out.exists()


def test_branch_worker_is_a_subprocess(tmp_path):
    worker = tmp_path / "worker.py"
    worker.write_text("import os\nfrom pathlib import Path\nPath('child.pid').write_text(str(os.getpid()))\n")
    run_branch(worker, tmp_path)
    child = int((tmp_path / "child.pid").read_text())
    assert child != __import__("os").getpid()


def test_length_sort_restores_ids():
    ids = np.array(["a", "b", "c"])
    lengths = np.array([1, 100, 5])
    sorted_ids, _order, restore = length_sort(ids, lengths)
    assert sorted_ids.tolist() == ["a", "c", "b"]
    assert unsort(sorted_ids, restore).tolist() == ["a", "b", "c"]


def test_simulate_projects_past_the_kernel_budget(tmp_path):
    train = pd.DataFrame({"id": ["1"], "text": ["hello"]})

    def hook(n_sample, frame):
        return 400.0, 1.5

    report = simulate_test(train, 25000, hook, tmp_path / "scale.json")
    assert report["projected_seconds"] == 40000
    assert report["projected_seconds"] > 8.5 * 3600


def test_pack_deps_dry_run_has_platform_flags(tmp_path):
    reqs = tmp_path / "reqs.txt"
    reqs.write_text("numpy\n")
    plan = pack_deps(reqs, tmp_path / "dataset_wheels", dry_run=True)
    assert "--platform manylinux2014_x86_64" in plan["cmd"]
    assert "--python-version 310" in plan["cmd"]
    assert "--only-binary=:all:" in plan["cmd"]
    assert "pip install --no-index --find-links=" in plan["snippet"]
    assert "dataset_wheels" in plan["snippet"]
