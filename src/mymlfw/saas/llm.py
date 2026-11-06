"""LLM / embedding gateway — only entry for external providers + spend caps.

No local torch / sentence-transformers weights. Unit tests use deterministic
hash embeddings; set ``MYMLFW_LLM_BASE_URL`` + ``MYMLFW_LLM_API_KEY`` for live.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from mymlfw.saas.db.client import pack_embedding_f32

EMBED_DIM = 64
_DEFAULT_COST_MICROS_PER_1K = 2_000


class LlmError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class LlmUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_micros: int = 0


@dataclass
class ChatResult:
    text: str
    usage: LlmUsage = field(default_factory=LlmUsage)
    model: str = "local-hash"


@dataclass
class EmbedResult:
    values: list[float]
    packed: Any  # BinaryVector
    usage: LlmUsage = field(default_factory=LlmUsage)
    model: str = "local-hash"


# Process-local DoW counters when Redis is unset.
_WINDOW: dict[str, list[float]] = {}
_ORG_INFLIGHT: dict[str, int] = {}


def _rate_limit(*, org_id: str, project_id: str, tool: str) -> None:
    """6/min/project, 2 concurrent/org (AGENTS). Redis when bound."""
    from mymlfw.saas.redis_control import llm_rate_limit_redis

    allowed = llm_rate_limit_redis(
        org_id=org_id, project_id=project_id, tool=tool, per_minute=6
    )
    if allowed is False:
        raise LlmError("llm_rate_limited", "6 LLM calls/min/project exceeded")
    if allowed is True:
        # Redis counted the hit; still enforce in-process concurrency.
        inflight = _ORG_INFLIGHT.get(org_id, 0)
        if inflight >= 2:
            raise LlmError("llm_concurrency", "2 concurrent LLM calls/org exceeded")
        return
    now = time.time()
    key = f"{org_id}:{project_id}:{tool}"
    hits = [t for t in _WINDOW.get(key, []) if now - t < 60.0]
    if len(hits) >= 6:
        raise LlmError("llm_rate_limited", "6 LLM calls/min/project exceeded")
    hits.append(now)
    _WINDOW[key] = hits
    inflight = _ORG_INFLIGHT.get(org_id, 0)
    if inflight >= 2:
        raise LlmError("llm_concurrency", "2 concurrent LLM calls/org exceeded")


def _begin(org_id: str) -> None:
    _ORG_INFLIGHT[org_id] = _ORG_INFLIGHT.get(org_id, 0) + 1


def _end(org_id: str) -> None:
    _ORG_INFLIGHT[org_id] = max(0, _ORG_INFLIGHT.get(org_id, 0) - 1)


def _hash_embed(text: str, *, dim: int = EMBED_DIM) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vals: list[float] = []
    for i in range(dim):
        b = digest[i % len(digest)]
        vals.append((b / 255.0) * 2.0 - 1.0)
    # L2 normalize
    norm = math.sqrt(sum(v * v for v in vals)) or 1.0
    return [v / norm for v in vals]


def _estimate_cost_micros(prompt_tokens: int, completion_tokens: int) -> int:
    total = prompt_tokens + completion_tokens
    return int(round((total / 1000.0) * _DEFAULT_COST_MICROS_PER_1K))


def embed_text(
    text: str,
    *,
    org_id: str = "org_local",
    project_id: str = "prj_local",
) -> EmbedResult:
    """Return float32 embedding packed for Mongo BinaryVector storage."""
    _rate_limit(org_id=org_id, project_id=project_id, tool="embed")
    _begin(org_id)
    try:
        base = os.environ.get("MYMLFW_LLM_BASE_URL", "").strip()
        key = os.environ.get("MYMLFW_LLM_API_KEY", "").strip()
        if base and key:
            return _embed_http(text, base_url=base, api_key=key)
        values = _hash_embed(text)
        tokens = max(1, len(text.split()))
        usage = LlmUsage(
            prompt_tokens=tokens,
            cost_micros=_estimate_cost_micros(tokens, 0),
        )
        return EmbedResult(
            values=values,
            packed=pack_embedding_f32(values),
            usage=usage,
            model="local-hash",
        )
    finally:
        _end(org_id)


def _embed_http(text: str, *, base_url: str, api_key: str) -> EmbedResult:
    url = base_url.rstrip("/") + "/embeddings"
    body = json.dumps(
        {"input": text, "model": os.environ.get("MYMLFW_EMBED_MODEL", "text-embedding-3-small")}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise LlmError("embed_http_failed", str(exc)) from exc
    data = (payload.get("data") or [{}])[0]
    values = [float(v) for v in (data.get("embedding") or [])]
    if not values:
        raise LlmError("embed_empty", "provider returned empty embedding")
    usage_raw = payload.get("usage") or {}
    pt = int(usage_raw.get("prompt_tokens") or max(1, len(text.split())))
    usage = LlmUsage(prompt_tokens=pt, cost_micros=_estimate_cost_micros(pt, 0))
    return EmbedResult(
        values=values,
        packed=pack_embedding_f32(values),
        usage=usage,
        model=str(payload.get("model") or "remote"),
    )


def chat_completion(
    *,
    system: str,
    user: str,
    org_id: str = "org_local",
    project_id: str = "prj_local",
    tool: str = "advise",
    max_tokens: int = 512,
) -> ChatResult:
    """Chat completion; local fallback is a structured template (no external call)."""
    _rate_limit(org_id=org_id, project_id=project_id, tool=tool)
    _begin(org_id)
    try:
        base = os.environ.get("MYMLFW_LLM_BASE_URL", "").strip()
        key = os.environ.get("MYMLFW_LLM_API_KEY", "").strip()
        if base and key:
            return _chat_http(
                system=system,
                user=user,
                base_url=base,
                api_key=key,
                max_tokens=max_tokens,
            )
        # Deterministic local brief for CI / offline.
        text = (
            f"## Advise\nTask: {user[:240]}\n\n"
            f"System context (truncated):\n{system[:800]}\n\n"
            "Propose one low-risk probe citing verified memory IDs only.\n"
        )
        pt = max(1, len(system.split()) + len(user.split()))
        ct = max(1, len(text.split()))
        return ChatResult(
            text=text,
            usage=LlmUsage(
                prompt_tokens=pt,
                completion_tokens=ct,
                cost_micros=_estimate_cost_micros(pt, ct),
            ),
            model="local-template",
        )
    finally:
        _end(org_id)


def _chat_http(
    *,
    system: str,
    user: str,
    base_url: str,
    api_key: str,
    max_tokens: int,
) -> ChatResult:
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps(
        {
            "model": os.environ.get("MYMLFW_CHAT_MODEL", "gpt-4o-mini"),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise LlmError("chat_http_failed", str(exc)) from exc
    choice = (payload.get("choices") or [{}])[0]
    text = str((choice.get("message") or {}).get("content") or "")
    usage_raw = payload.get("usage") or {}
    pt = int(usage_raw.get("prompt_tokens") or 0)
    ct = int(usage_raw.get("completion_tokens") or 0)
    return ChatResult(
        text=text,
        usage=LlmUsage(
            prompt_tokens=pt,
            completion_tokens=ct,
            cost_micros=_estimate_cost_micros(pt, ct),
        ),
        model=str(payload.get("model") or "remote"),
    )


def reset_llm_limits_for_tests() -> None:
    _WINDOW.clear()
    _ORG_INFLIGHT.clear()
