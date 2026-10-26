"""Structured errors. The CLI prints to_dict() as one JSON object."""

from __future__ import annotations


class MymlfwError(Exception):
    def __init__(self, error_code: str, suggested_fix: str = "", **fields):
        self.error_code = error_code
        self.suggested_fix = suggested_fix
        self.fields = fields
        super().__init__(error_code)

    def to_dict(self) -> dict:
        out = {"error_code": self.error_code, "suggested_fix": self.suggested_fix}
        out.update(self.fields)
        return out


class DuplicateCandidateError(MymlfwError):
    def __init__(self, **fields):
        super().__init__(
            "DUPLICATE_CANDIDATE",
            "Enforce unique ranked candidates before scoring MRR.",
            **fields,
        )


class AlignmentError(MymlfwError):
    def __init__(self, suggested_fix: str = "", **fields):
        super().__init__(
            "ID_MISMATCH",
            suggested_fix or "Align every branch on the same set of ids.",
            **fields,
        )


class ClassOrderError(MymlfwError):
    def __init__(self, expected, got, file: str = "", target: str = "", **fields):
        fix = (
            "Run python -m mymlfw blend reorder-classes "
            f"--target {target} --source {file}"
        )
        super().__init__(
            "CLASS_ORDER_MISMATCH",
            fix,
            expected=list(expected),
            got=list(got),
            file=file,
            target=target,
            **fields,
        )


class PayloadTooLargeError(MymlfwError):
    def __init__(self, nbytes: int, **fields):
        super().__init__(
            "PAYLOAD_TOO_LARGE",
            "Keep notebook payloads under 512000 bytes. Ship weights as a Kaggle dataset.",
            nbytes=nbytes,
            max_payload_bytes=512_000,
            **fields,
        )
