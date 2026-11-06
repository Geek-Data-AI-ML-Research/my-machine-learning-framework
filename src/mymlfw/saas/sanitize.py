"""Unicode / HTML sanitize + untrusted-content spotlight."""

from __future__ import annotations

import html
import re
import unicodedata

_TAG = re.compile(r"<[^>]+>")
_CTRL = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f]")


def sanitize_untrusted(text: str, *, max_len: int = 8000) -> str:
    norm = unicodedata.normalize("NFKC", text or "")
    norm = _CTRL.sub("", norm)
    norm = _TAG.sub("", norm)
    norm = html.unescape(norm)
    # Second pass after unescape so encoded tags do not survive.
    norm = _TAG.sub("", norm)
    return norm[:max_len]


def spotlight_untrusted(text: str) -> str:
    clean = sanitize_untrusted(text)
    return f"<untrusted_kaggle_content>\n{clean}\n</untrusted_kaggle_content>"
