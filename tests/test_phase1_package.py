import json
import subprocess
import sys

import yaml


def test_version_prints_package_version():
    import mymlfw

    completed = subprocess.run(
        [sys.executable, "-m", "mymlfw", "version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == mymlfw.__version__


def test_yaml_imports_from_the_core_install():
    assert yaml.__version__


def test_unknown_command_is_json_without_a_traceback():
    completed = subprocess.run(
        [sys.executable, "-m", "mymlfw", "nope"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stderr)
    assert payload["error_code"]
    assert payload["suggested_fix"]
    assert "traceback" not in payload
    assert "Traceback" not in completed.stderr


def test_debug_adds_a_traceback_field():
    completed = subprocess.run(
        [sys.executable, "-m", "mymlfw", "--debug", "nope"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stderr)
    assert "traceback" in payload
