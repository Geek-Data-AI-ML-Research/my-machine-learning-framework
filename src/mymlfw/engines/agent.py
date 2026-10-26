"""Pack an agent directory. Host Python files are refused."""

from __future__ import annotations

from pathlib import Path

from mymlfw.errors import MymlfwError
from mymlfw.submit.zippack import zip_bundle


class AgentZipEngine:
    def prepare(self, frame):
        return frame

    def package(self, directory, out_zip, model_pin: str | None = None) -> dict:
        directory = Path(directory)
        host = [path.relative_to(directory).as_posix() for path in directory.rglob("*.py")]
        if host:
            raise MymlfwError(
                "HOST_CODE",
                "Remove host Python from the agent bundle. The kernel does not run it.",
                files=host,
            )
        if model_pin:
            pin = directory / "model_pin.txt"
            if not pin.exists() or pin.read_text().strip() != model_pin:
                raise MymlfwError(
                    "MODEL_PIN",
                    "Write model_pin.txt with the exact model id before packing.",
                    expected=model_pin,
                )
        return zip_bundle(directory, out_zip)
