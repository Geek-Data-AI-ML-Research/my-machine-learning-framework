"""Post-advise citation firewall — only verified IDs reach UI/CLI/MCP."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

_ID_RE = re.compile(
    r"\b((?:exp_|ded_|gol_|mem_|epc_|axm_|msn_)[0-9A-HJKMNP-TV-Z]{26})\b"
)


@dataclass
class CitationFirewallResult:
    brief_md: str
    proposed_missions: list[dict[str, Any]]
    verified_ids: list[str] = field(default_factory=list)
    stripped_ids: list[str] = field(default_factory=list)
    grounding_score: float = 0.0
    times_cited_incs: list[str] = field(default_factory=list)


def harvest_ids(*texts: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for match in _ID_RE.findall(text or ""):
            if match not in seen:
                seen.add(match)
                found.append(match)
    return found


def enforce_citation_firewall(
    *,
    brief_md: str,
    proposed_missions: list[dict[str, Any]],
    fetch_docs: Callable[[list[str]], dict[str, dict[str, Any]]],
) -> CitationFirewallResult:
    """Strip hallucinated ULIDs; inject ``[DB-VERIFIED …]`` on first mention."""
    mission_blobs = []
    for m in proposed_missions:
        mission_blobs.append(str(m.get("rationale_md") or ""))
        mission_blobs.append(str(m.get("title") or ""))
        for cid in m.get("cited_ids") or []:
            mission_blobs.append(str(cid))
    attempted = harvest_ids(brief_md, *mission_blobs)
    for m in proposed_missions:
        gid = m.get("goal_id")
        if gid is None:
            continue
        gid_s = str(gid)
        if gid_s and gid_s not in attempted:
            attempted.append(gid_s)
    docs = fetch_docs(attempted) if attempted else {}
    # Grounding score counts prose/cited harvest only (not silent goal_id fetch).
    harvested = harvest_ids(brief_md, *mission_blobs)
    verified = [i for i in harvested if i in docs]
    stripped = [i for i in harvested if i not in docs]
    grounding = (len(verified) / len(attempted)) if attempted else 1.0

    cleaned_brief = brief_md
    for bad in stripped:
        cleaned_brief = cleaned_brief.replace(
            bad, f"[UNVERIFIED-ID-STRIPPED:{bad}]"
        )
    seen_badge: set[str] = set()
    for good in verified:
        doc = docs[good]
        badge = _badge_for(doc)
        if good not in seen_badge and good in cleaned_brief:
            cleaned_brief = cleaned_brief.replace(
                good, f"{good} {badge}", 1
            )
            seen_badge.add(good)

    cleaned_missions: list[dict[str, Any]] = []
    for m in proposed_missions:
        row = dict(m)
        rationale = str(row.get("rationale_md") or "")
        for bad in stripped:
            rationale = rationale.replace(bad, f"[UNVERIFIED-ID-STRIPPED:{bad}]")
        cited = [c for c in (row.get("cited_ids") or []) if c in docs]
        row["rationale_md"] = rationale
        row["cited_ids"] = cited
        goal_id = row.get("goal_id")
        if goal_id and str(goal_id) not in docs and str(goal_id).startswith("gol_"):
            # Drop missions pointing at hallucinated goals.
            continue
        if goal_id and str(goal_id) in docs:
            g = docs[str(goal_id)]
            thr = g.get("threshold")
            if thr is not None and "threshold" not in rationale.lower():
                row["rationale_md"] = (
                    f"{rationale}\n\n[DB-VERIFIED goal threshold={thr}]"
                ).strip()
        cleaned_missions.append(row)

    return CitationFirewallResult(
        brief_md=cleaned_brief,
        proposed_missions=cleaned_missions,
        verified_ids=verified,
        stripped_ids=stripped,
        grounding_score=grounding,
        times_cited_incs=[i for i in verified if i.startswith(("ded_", "mem_", "epc_"))],
    )


def _badge_for(doc: dict[str, Any]) -> str:
    kind = str(doc.get("doc_type") or doc.get("kind") or "doc")
    parts = [f"[DB-VERIFIED {kind}"]
    if doc.get("cv_mean") is not None:
        parts.append(f"cv={doc['cv_mean']}")
    if doc.get("verdict"):
        parts.append(f"verdict={doc['verdict']}")
    if doc.get("threshold") is not None:
        parts.append(f"threshold={doc['threshold']}")
    if doc.get("status"):
        parts.append(f"status={doc['status']}")
    return " ".join(parts) + "]"
