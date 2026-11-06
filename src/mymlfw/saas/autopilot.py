"""Night-Shift Autopilot: budgeted multi-fidelity MCTS + successive halving.

Sessions (``aps_``) hold scalars/counters only. Probes live in separate
``autopilot_nodes`` (``nd_``) docs — never embedded ``nodes[]`` arrays.
Unified mutex: ``projects.active_execution_lock`` with ``holder_type=autopilot``.
Behind org feature flag ``night_shift``. Never auto-submits to Kaggle.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Sequence

from mymlfw.saas.ids import new_autopilot_node_id, new_autopilot_session_id
from mymlfw.saas.lever_verifier import LeverVerifierResult, verify_lever_mutation

FEATURE_FLAG = "night_shift"
BOARD_WIDTH = 88

AutopilotMode = Literal[
    "grandmaster_sweep",
    "feature_evolution",
    "paradigm_explorer",
    "loss_and_postproc",
]
SessionStatus = Literal["running", "paused", "halted", "completed"]
NodeStatus = Literal[
    "pending",
    "running",
    "advanced",
    "pruned",
    "promoted",
    "dead_end",
    "failed_infra",
]
Rung = Literal[0, 1, 2]
HalvingAction = Literal["advance", "prune", "promote", "retry"]

STAGNATION_PIVOT_THRESHOLD = 8
INFRA_HALT_THRESHOLD = 3
# Rung-1 diversity-enabler: advance when Spearman corr to pool is below this
# even if Fold-0 did not beat baseline (near-baseline CV).
DIVERSITY_CORR_THRESHOLD = 0.88
DEFAULT_UCT_C = math.sqrt(2.0)
DEFAULT_DIVERSITY_LAMBDA = 1.0
USD_MICROS = 1_000_000
SPOT_PREEMPTION_REASONS = frozenset(
    {"spot_preempted", "spot_preempted_requeue", "aws_spot_interruption"}
)

MODES: tuple[AutopilotMode, ...] = (
    "grandmaster_sweep",
    "feature_evolution",
    "paradigm_explorer",
    "loss_and_postproc",
)


class AutopilotError(Exception):
    """Control-plane Autopilot failure."""

    def __init__(self, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"error_code": self.code, "message": self.message}
        body.update(self.extra)
        return body


def usd_to_micros(usd: float) -> int:
    """CLI dollars → Int64 ``*_cost_micros`` (never store float USD)."""
    if not math.isfinite(usd) or usd < 0:
        raise AutopilotError("invalid_budget_usd", "max_llm_usd must be a finite non-negative number")
    return int(round(usd * USD_MICROS))


def micros_to_usd_display(micros: int) -> str:
    return f"${micros / USD_MICROS:.4f}"


@dataclass
class AutopilotNode:
    """One MCTS probe stored as a separate ``nd_`` document."""

    id: str
    session_id: str
    parent_id: str | None
    rung: int = 0
    visits: int = 0
    status: NodeStatus = "pending"
    variable: str = ""
    cv_delta: float = 0.0
    cv_std: float = 1.0
    fold0_delta: float = 0.0
    max_spearman_to_pool: float = 1.0
    smoke_ok: bool | None = None
    integrity_ok: bool | None = None
    is_root: bool = False
    worktree: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for key in ("created_at", "updated_at"):
            val = d.get(key)
            if isinstance(val, datetime):
                d[key] = val.isoformat()
        return d


@dataclass
class AutopilotSession:
    """Parent ``aps_`` scalars only — no embedded node arrays."""

    id: str
    workspace_id: str
    project_id: str
    mode: AutopilotMode = "grandmaster_sweep"
    status: SessionStatus = "running"
    feature_flag: str = FEATURE_FLAG
    # Budgets (micros / counts / hours)
    max_wall_hours: float = 8.0
    max_probes: int = 64
    max_gpu_hours: float = 8.0
    max_llm_cost_micros: int = 5_000_000
    spent_llm_cost_micros: int = 0
    spent_gpu_hours: float = 0.0
    probes_launched: int = 0
    # Funnel counters
    r0_pass: int = 0
    r0_fail: int = 0
    r1_advance: int = 0
    r1_prune: int = 0
    r2_promote: int = 0
    # Circuit breakers
    stagnant_r1_streak: int = 0
    infra_fail_count: int = 0
    pivot_count: int = 0
    halt_reason: str | None = None
    # Pointers (ids only)
    root_node_id: str | None = None
    best_node_id: str | None = None
    baseline_cv: float = 0.0
    # Lock bookkeeping (also mirrored on projects.active_execution_lock)
    lock_holder_type: Literal["autopilot"] = "autopilot"
    lock_expires_at: datetime | None = None
    started_at: datetime | None = None
    updated_at: datetime | None = None
    morning_digest: str | None = None
    auto_kaggle_submit: Literal[False] = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for key in ("lock_expires_at", "started_at", "updated_at"):
            val = d.get(key)
            if isinstance(val, datetime):
                d[key] = val.isoformat()
        # Never embed nodes on the session payload.
        d.pop("nodes", None)
        return d


@dataclass(frozen=True)
class HalvingDecision:
    action: HalvingAction
    rung: int
    reason: str
    diversity_enabled: bool = False


@dataclass(frozen=True)
class UctSelection:
    node_id: str
    score: float
    exploit: float
    diversity_bonus: float
    explore: float


@dataclass(frozen=True)
class ExecutionLockState:
    holder_type: Literal["lever", "autopilot"]
    holder_id: str
    expires_at: datetime


def select_next_parent_node_uct(
    nodes: Sequence[AutopilotNode | dict[str, Any]],
    *,
    c: float = DEFAULT_UCT_C,
    diversity_lambda: float = DEFAULT_DIVERSITY_LAMBDA,
    mode: AutopilotMode = "grandmaster_sweep",
) -> UctSelection | None:
    """Pick the next expansion parent via UCT + diversity bonus.

    score = (CVΔ / σ) + λ·(1 − max_Spearman_to_pool) + c·√(ln N / n)

    ``paradigm_explorer`` doubles λ so OOF-orthogonal probes win even with
    slightly lower CVΔ. Unvisited expandable nodes score as +inf.
    """
    pool = [_coerce_node(n) for n in nodes]
    expandable = [
        n
        for n in pool
        if n.status in ("pending", "advanced", "promoted")
        or (n.is_root and n.status != "pruned")
    ]
    # Prefer parents that can still spawn children (not pruned / dead_end).
    candidates = [
        n
        for n in pool
        if n.status not in ("pruned", "dead_end", "failed_infra")
        and n.rung < 2
    ]
    if not candidates:
        candidates = [n for n in expandable if n.status not in ("pruned", "dead_end")]
    if not candidates:
        return None

    total_n = sum(max(0, n.visits) for n in pool) or 1
    log_n = math.log(max(total_n, 1))
    lam = diversity_lambda * (2.0 if mode == "paradigm_explorer" else 1.0)

    best: UctSelection | None = None
    for node in candidates:
        n_vis = max(0, int(node.visits))
        sigma = abs(float(node.cv_std)) if abs(float(node.cv_std)) > 1e-12 else 1.0
        exploit = float(node.cv_delta) / sigma
        corr = min(1.0, max(0.0, float(node.max_spearman_to_pool)))
        diversity_bonus = lam * (1.0 - corr)
        if n_vis == 0:
            explore = float("inf")
            score = float("inf")
        else:
            explore = c * math.sqrt(log_n / n_vis)
            score = exploit + diversity_bonus + explore
        sel = UctSelection(
            node_id=node.id,
            score=score,
            exploit=exploit,
            diversity_bonus=diversity_bonus,
            explore=explore if math.isfinite(explore) else 1e18,
        )
        if best is None or sel.score > best.score:
            best = sel
    return best


def evaluate_successive_halving_rung(
    *,
    rung: int,
    smoke_ok: bool | None = None,
    fold0_delta: float = 0.0,
    max_spearman_to_pool: float = 1.0,
    cv_delta: float = 0.0,
    integrity_ok: bool | None = None,
    diversity_corr_threshold: float = DIVERSITY_CORR_THRESHOLD,
) -> HalvingDecision:
    """R0→R1→R2 successive-halving gate.

    * R0: micro smoke — fail → prune/dead_end; pass → advance to R1.
    * R1: Fold-0 beat **or** diversity-enabler (corr < threshold near baseline).
    * R2: full CV + integrity — promote when both ok and cv_delta ≥ 0.
    """
    if rung == 0:
        if smoke_ok is False:
            return HalvingDecision("prune", 0, "r0_smoke_fail")
        if smoke_ok is True:
            return HalvingDecision("advance", 0, "r0_smoke_pass")
        return HalvingDecision("retry", 0, "r0_smoke_pending")

    if rung == 1:
        beat = fold0_delta > 0.0
        diverse = max_spearman_to_pool < diversity_corr_threshold
        # Near-baseline: allow diversity advance when Fold-0 is not a clear loss.
        near_baseline = fold0_delta >= -0.002
        if beat:
            return HalvingDecision("advance", 1, "r1_fold0_beat", diversity_enabled=False)
        if diverse and near_baseline:
            return HalvingDecision(
                "advance",
                1,
                "r1_diversity_enabler",
                diversity_enabled=True,
            )
        return HalvingDecision("prune", 1, "r1_no_beat_no_diversity")

    if rung == 2:
        if integrity_ok is False:
            return HalvingDecision("prune", 2, "r2_integrity_fail")
        if integrity_ok is True and cv_delta >= 0.0:
            return HalvingDecision("promote", 2, "r2_full_cv_ok")
        if integrity_ok is None:
            return HalvingDecision("retry", 2, "r2_integrity_pending")
        return HalvingDecision("prune", 2, "r2_cv_regression")

    raise AutopilotError("invalid_rung", f"rung must be 0|1|2, got {rung}")


def is_spot_preemption(reason: str | None) -> bool:
    if not reason:
        return False
    return reason.strip().lower() in SPOT_PREEMPTION_REASONS


def apply_infra_failure(
    session: AutopilotSession,
    *,
    reason: str,
    threshold: int = INFRA_HALT_THRESHOLD,
    store: InMemoryAutopilotStore | None = None,
) -> AutopilotSession:
    """Increment infra strikes unless Spot preemption (excluded from 3-strike halt)."""
    if is_spot_preemption(reason):
        session.notes.append(f"spot_preempted_requeue:{reason}")
        session.updated_at = datetime.now(UTC)
        return session
    session.infra_fail_count += 1
    session.notes.append(f"infra_fail:{reason}:strike={session.infra_fail_count}")
    if session.infra_fail_count >= threshold:
        session.status = "halted"
        session.halt_reason = f"infra_halt:{session.infra_fail_count}_strikes"
        session.notes.append("webhook:autopilot.halt.infra")
        if store is not None:
            _release_lock(store, session.workspace_id, session.project_id, session.id)
    session.updated_at = datetime.now(UTC)
    return session


def apply_r1_stagnation(
    session: AutopilotSession,
    *,
    advanced: bool,
    threshold: int = STAGNATION_PIVOT_THRESHOLD,
) -> AutopilotSession:
    """8× stagnant Rung-1 → consolidate + pivot (counter reset)."""
    if advanced:
        session.stagnant_r1_streak = 0
    else:
        session.stagnant_r1_streak += 1
        if session.stagnant_r1_streak >= threshold:
            session.pivot_count += 1
            session.stagnant_r1_streak = 0
            session.notes.append(
                "stagnation_pivot:consolidate_project_brain"
            )
    session.updated_at = datetime.now(UTC)
    return session


def budget_remaining(session: AutopilotSession, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    if session.status in ("halted", "paused", "completed"):
        return False
    if session.probes_launched >= session.max_probes:
        return False
    if session.spent_llm_cost_micros >= session.max_llm_cost_micros:
        return False
    if session.spent_gpu_hours >= session.max_gpu_hours:
        return False
    if session.started_at is not None:
        elapsed_h = (now - session.started_at).total_seconds() / 3600.0
        if elapsed_h >= session.max_wall_hours:
            return False
    return True


def gate_mutation(
    *,
    variable: str,
    parent_node_id: str | None,
    mode: AutopilotMode,
) -> LeverVerifierResult:
    """Always call lever_verifier on LLM-driven mutations (structural + optional LLM)."""
    return verify_lever_mutation(
        variable=variable,
        parent_node_id=parent_node_id,
        mode=mode,
    )


def render_morning_digest_ascii(session: AutopilotSession, nodes: Sequence[AutopilotNode]) -> str:
    """Morning wake-up digest board (fps={{0}} — static, human CTAs only)."""
    w = BOARD_WIDTH
    lines = [
        "=" * w,
        "NIGHT-SHIFT AUTOPILOT — morning digest (fps=0)".ljust(w)[:w],
        f"session {session.id}  mode={session.mode}  status={session.status}".ljust(w)[:w],
        "-" * w,
        (
            f"funnel  R0 pass/fail={session.r0_pass}/{session.r0_fail}  "
            f"R1 adv/prune={session.r1_advance}/{session.r1_prune}  "
            f"R2 promote={session.r2_promote}"
        ).ljust(w)[:w],
        (
            f"budget  probes={session.probes_launched}/{session.max_probes}  "
            f"llm={micros_to_usd_display(session.spent_llm_cost_micros)}"
            f"/{micros_to_usd_display(session.max_llm_cost_micros)}  "
            f"gpu_h={session.spent_gpu_hours:.2f}/{session.max_gpu_hours:.2f}"
        ).ljust(w)[:w],
        (
            f"breakers  stagnant_r1={session.stagnant_r1_streak}  "
            f"infra={session.infra_fail_count}/{INFRA_HALT_THRESHOLD}  "
            f"pivots={session.pivot_count}"
        ).ljust(w)[:w],
        f"best_node  {session.best_node_id or '-'}".ljust(w)[:w],
        "-" * w,
        "tree (promotes / prunes)".ljust(w)[:w],
    ]
    by_parent: dict[str | None, list[AutopilotNode]] = {}
    for n in nodes:
        by_parent.setdefault(n.parent_id, []).append(n)
    roots = [n for n in nodes if n.is_root or n.parent_id is None]
    if not roots and nodes:
        roots = list(nodes)[:1]

    def _walk(node: AutopilotNode, depth: int) -> None:
        mark = {
            "promoted": "+",
            "pruned": "x",
            "dead_end": "x",
            "advanced": ">",
            "failed_infra": "!",
        }.get(node.status, ".")
        indent = "  " * depth
        lines.append(
            f"{indent}{mark} {node.id[-8:]} r{node.rung} "
            f"Δ={node.cv_delta:+.4f} corr={node.max_spearman_to_pool:.2f} "
            f"{node.variable or '(root)'} [{node.status}]".ljust(w)[:w]
        )
        for child in by_parent.get(node.id, []):
            _walk(child, depth + 1)

    for root in roots:
        _walk(root, 0)

    lines.extend(
        [
            "-" * w,
            "CTAs (human only — Autopilot never auto-submits to Kaggle)".ljust(w)[:w],
            "  [1] promote blend → baseline".ljust(w)[:w],
            "  [2] queue Kaggle submit (requires human approve)".ljust(w)[:w],
            "  [3] view diff / worktree".ljust(w)[:w],
            f"auto_kaggle_submit={session.auto_kaggle_submit}".ljust(w)[:w],
            "=" * w,
        ]
    )
    session.morning_digest = "\n".join(lines)
    return session.morning_digest


def _coerce_node(raw: AutopilotNode | dict[str, Any]) -> AutopilotNode:
    if isinstance(raw, AutopilotNode):
        return raw
    return AutopilotNode(
        id=str(raw["id"]),
        session_id=str(raw.get("session_id") or ""),
        parent_id=raw.get("parent_id"),
        rung=int(raw.get("rung") or 0),
        visits=int(raw.get("visits") or 0),
        status=raw.get("status") or "pending",  # type: ignore[arg-type]
        variable=str(raw.get("variable") or ""),
        cv_delta=float(raw.get("cv_delta") or 0.0),
        cv_std=float(raw.get("cv_std") if raw.get("cv_std") is not None else 1.0),
        fold0_delta=float(raw.get("fold0_delta") or 0.0),
        max_spearman_to_pool=float(
            raw.get("max_spearman_to_pool")
            if raw.get("max_spearman_to_pool") is not None
            else 1.0
        ),
        smoke_ok=raw.get("smoke_ok"),
        integrity_ok=raw.get("integrity_ok"),
        is_root=bool(raw.get("is_root")),
        worktree=raw.get("worktree"),
    )


# ---------------------------------------------------------------------------
# In-memory store (unit tests / API without Mongo)
# ---------------------------------------------------------------------------


def execution_lock_key(workspace_id: str, project_id: str) -> str:
    """Tenant-scoped mutex key — never key locks on project_id alone."""
    return f"{workspace_id}:{project_id}"


class InMemoryAutopilotStore:
    """Process-local sessions + nodes (mirrors separate Mongo collections)."""

    def __init__(self) -> None:
        self.sessions: dict[str, AutopilotSession] = {}
        self.nodes: dict[str, AutopilotNode] = {}
        # ``{workspace_id}:{project_id}`` → active_execution_lock
        self.locks: dict[str, ExecutionLockState] = {}

    def nodes_for_session(self, session_id: str) -> list[AutopilotNode]:
        return [n for n in self.nodes.values() if n.session_id == session_id]

    def active_session_for_project(
        self, project_id: str, *, workspace_id: str | None = None
    ) -> AutopilotSession | None:
        for s in self.sessions.values():
            if s.project_id != project_id or s.status not in ("running", "paused"):
                continue
            if workspace_id and s.workspace_id != workspace_id:
                continue
            return s
        return None


_GLOBAL_STORE = InMemoryAutopilotStore()


def get_autopilot_store() -> InMemoryAutopilotStore:
    return _GLOBAL_STORE


def reset_autopilot_store() -> InMemoryAutopilotStore:
    global _GLOBAL_STORE
    _GLOBAL_STORE = InMemoryAutopilotStore()
    return _GLOBAL_STORE


def _require_night_shift(night_shift_enabled: bool) -> None:
    if not night_shift_enabled:
        raise AutopilotError(
            "feature_flag_disabled",
            "Enable org feature_flags.night_shift before starting Autopilot.",
            feature_flag=FEATURE_FLAG,
            suggested_fix="Set feature_flags.night_shift=true on the org.",
        )


def start_autopilot(
    *,
    workspace_id: str,
    project_id: str,
    mode: AutopilotMode = "grandmaster_sweep",
    hours: float = 8.0,
    max_probes: int = 64,
    max_gpu_hours: float = 8.0,
    max_llm_cost_micros: int | None = None,
    max_llm_usd: float | None = None,
    baseline_cv: float = 0.0,
    night_shift_enabled: bool = True,
    store: InMemoryAutopilotStore | None = None,
    lock_hours: float = 12.0,
) -> dict[str, Any]:
    """Seed root node + acquire ``active_execution_lock`` (autopilot)."""
    _require_night_shift(night_shift_enabled)
    if mode not in MODES:
        raise AutopilotError("invalid_mode", f"mode must be one of {MODES}")
    store = store or get_autopilot_store()
    lock_key = execution_lock_key(workspace_id, project_id)

    existing = store.active_session_for_project(
        project_id, workspace_id=workspace_id
    )
    if existing is not None:
        raise AutopilotError(
            "session_already_active",
            f"Project already has Autopilot session {existing.id} ({existing.status}).",
            session_id=existing.id,
        )

    lock = store.locks.get(lock_key)
    now = datetime.now(UTC)
    if lock is not None and lock.expires_at > now:
        raise AutopilotError(
            "execution_lock_held",
            f"active_execution_lock held by {lock.holder_type}:{lock.holder_id}",
            holder_type=lock.holder_type,
            holder_id=lock.holder_id,
        )

    if max_llm_cost_micros is None:
        max_llm_cost_micros = (
            usd_to_micros(max_llm_usd) if max_llm_usd is not None else 5_000_000
        )

    session_id = new_autopilot_session_id()
    root_id = new_autopilot_node_id()
    expires = now + timedelta(hours=lock_hours)

    session = AutopilotSession(
        id=session_id,
        workspace_id=workspace_id,
        project_id=project_id,
        mode=mode,
        status="running",
        max_wall_hours=float(hours),
        max_probes=int(max_probes),
        max_gpu_hours=float(max_gpu_hours),
        max_llm_cost_micros=int(max_llm_cost_micros),
        root_node_id=root_id,
        best_node_id=root_id,
        baseline_cv=float(baseline_cv),
        lock_expires_at=expires,
        started_at=now,
        updated_at=now,
        auto_kaggle_submit=False,
    )
    root = AutopilotNode(
        id=root_id,
        session_id=session_id,
        parent_id=None,
        rung=0,
        visits=1,
        status="advanced",
        variable="baseline",
        cv_delta=0.0,
        cv_std=1.0,
        is_root=True,
        worktree=None,
        created_at=now,
        updated_at=now,
    )
    store.sessions[session_id] = session
    store.nodes[root_id] = root
    store.locks[lock_key] = ExecutionLockState(
        holder_type="autopilot",
        holder_id=session_id,
        expires_at=expires,
    )
    return {
        "status": "running",
        "session": session.to_dict(),
        "root_node": root.to_dict(),
        "feature_flag": FEATURE_FLAG,
        "active_execution_lock": {
            "holder_type": "autopilot",
            "holder_id": session_id,
            "expires_at": expires.isoformat(),
        },
        "auto_kaggle_submit": False,
    }


def get_autopilot_status(
    *,
    project_id: str,
    session_id: str | None = None,
    workspace_id: str | None = None,
    store: InMemoryAutopilotStore | None = None,
) -> dict[str, Any]:
    store = store or get_autopilot_store()
    session = None
    if session_id:
        session = store.sessions.get(session_id)
        if session is not None and session.project_id != project_id:
            session = None
        if (
            session is not None
            and workspace_id
            and session.workspace_id != workspace_id
        ):
            session = None
    if session is None:
        session = store.active_session_for_project(
            project_id, workspace_id=workspace_id
        )
    if session is None:
        # Fall back to most recent for project (tenant-scoped when workspace given).
        candidates = [
            s
            for s in store.sessions.values()
            if s.project_id == project_id
            and (not workspace_id or s.workspace_id == workspace_id)
        ]
        session = max(
            candidates,
            key=lambda s: s.started_at or datetime.min.replace(tzinfo=UTC),
            default=None,
        )
    if session is None:
        raise AutopilotError("session_not_found", "No Autopilot session for project.")
    nodes = store.nodes_for_session(session.id)
    lock = store.locks.get(
        execution_lock_key(session.workspace_id, session.project_id)
    )
    return {
        "status": session.status,
        "session": session.to_dict(),
        "node_count": len(nodes),
        # Cap projection — full history lives in autopilot_nodes collection.
        "nodes": [n.to_dict() for n in nodes[:64]],
        "budget_remaining": budget_remaining(session),
        "active_execution_lock": (
            {
                "holder_type": lock.holder_type,
                "holder_id": lock.holder_id,
                "expires_at": lock.expires_at.isoformat(),
            }
            if lock
            else None
        ),
        "feature_flag": FEATURE_FLAG,
        "auto_kaggle_submit": False,
    }


def pause_autopilot(
    *,
    project_id: str,
    session_id: str | None = None,
    workspace_id: str | None = None,
    store: InMemoryAutopilotStore | None = None,
) -> dict[str, Any]:
    store = store or get_autopilot_store()
    session = _resolve_session(
        store, project_id, session_id, workspace_id=workspace_id
    )
    if session.status != "running":
        raise AutopilotError(
            "invalid_state",
            f"Cannot pause session in status={session.status}",
        )
    session.status = "paused"
    session.updated_at = datetime.now(UTC)
    return {"status": "paused", "session": session.to_dict()}


def resume_autopilot(
    *,
    project_id: str,
    session_id: str | None = None,
    night_shift_enabled: bool = True,
    workspace_id: str | None = None,
    store: InMemoryAutopilotStore | None = None,
) -> dict[str, Any]:
    _require_night_shift(night_shift_enabled)
    store = store or get_autopilot_store()
    session = _resolve_session(
        store, project_id, session_id, workspace_id=workspace_id
    )
    if session.status == "halted":
        raise AutopilotError("halted", "Halted session cannot resume; start a new session.")
    if session.status not in ("paused", "running"):
        raise AutopilotError(
            "invalid_state",
            f"Cannot resume session in status={session.status}",
        )
    session.status = "running"
    session.updated_at = datetime.now(UTC)
    return {"status": "running", "session": session.to_dict()}


def halt_autopilot(
    *,
    project_id: str,
    session_id: str | None = None,
    workspace_id: str | None = None,
    reason: str = "operator_halt",
    store: InMemoryAutopilotStore | None = None,
) -> dict[str, Any]:
    """Mark session halted and release ``active_execution_lock``."""
    store = store or get_autopilot_store()
    session = _resolve_session(
        store, project_id, session_id, workspace_id=workspace_id
    )
    if session.status in ("halted", "completed"):
        _release_lock(store, session.workspace_id, session.project_id, session.id)
        return {"status": session.status, "session": session.to_dict()}
    session.status = "halted"
    session.halt_reason = reason
    session.updated_at = datetime.now(UTC)
    _release_lock(store, session.workspace_id, session.project_id, session.id)
    return {"status": "halted", "session": session.to_dict()}


def digest_autopilot(
    *,
    project_id: str,
    session_id: str | None = None,
    workspace_id: str | None = None,
    store: InMemoryAutopilotStore | None = None,
) -> dict[str, Any]:
    store = store or get_autopilot_store()
    session = _resolve_session(
        store, project_id, session_id, workspace_id=workspace_id
    )
    nodes = store.nodes_for_session(session.id)
    board = render_morning_digest_ascii(session, nodes)
    return {
        "status": session.status,
        "session_id": session.id,
        "ascii_board": board,
        "cta": [
            "promote_blend_to_baseline",
            "queue_kaggle_submit_human",
            "view_diff",
        ],
        "auto_kaggle_submit": False,
        "feature_flag": FEATURE_FLAG,
    }


def _release_lock(
    store: InMemoryAutopilotStore,
    workspace_id: str,
    project_id: str,
    session_id: str,
) -> None:
    key = execution_lock_key(workspace_id, project_id)
    lock = store.locks.get(key)
    if lock is not None and lock.holder_id == session_id:
        store.locks.pop(key, None)


def rollback_autopilot_start(
    *,
    workspace_id: str,
    project_id: str,
    session_id: str,
    store: InMemoryAutopilotStore | None = None,
) -> None:
    """Undo in-memory session+lock after a failed Mongo acquire (start saga)."""
    store = store or get_autopilot_store()
    session = store.sessions.get(session_id)
    if session is not None and session.workspace_id == workspace_id:
        for nid in list(store.nodes.keys()):
            node = store.nodes.get(nid)
            if node is not None and node.session_id == session_id:
                store.nodes.pop(nid, None)
        store.sessions.pop(session_id, None)
    _release_lock(store, workspace_id, project_id, session_id)


def expire_wall_budget_if_needed(
    *,
    project_id: str,
    session_id: str | None = None,
    workspace_id: str | None = None,
    store: InMemoryAutopilotStore | None = None,
) -> dict[str, Any] | None:
    """If wall clock exceeded on a running session, complete + release in-memory lock.

    Returns the completion payload when a transition happened; else None.
    Callers with Mongo must also ``release_execution_lock``.
    """
    store = store or get_autopilot_store()
    try:
        session = _resolve_session(
            store, project_id, session_id, workspace_id=workspace_id
        )
    except AutopilotError:
        return None
    if session.status != "running":
        return None
    if budget_remaining(session):
        return None
    session.status = "completed"
    session.halt_reason = session.halt_reason or "budget_exhausted"
    session.updated_at = datetime.now(UTC)
    _release_lock(store, session.workspace_id, project_id, session.id)
    board = render_morning_digest_ascii(session, store.nodes_for_session(session.id))
    return {
        "status": "completed",
        "reason": "budget_exhausted",
        "session": session.to_dict(),
        "session_id": session.id,
        "ascii_board": board,
        "auto_kaggle_submit": False,
        "lock_released": True,
    }


def _resolve_session(
    store: InMemoryAutopilotStore,
    project_id: str,
    session_id: str | None,
    *,
    workspace_id: str | None = None,
) -> AutopilotSession:
    if session_id:
        session = store.sessions.get(session_id)
        if session is None or session.project_id != project_id:
            raise AutopilotError("session_not_found", f"Unknown session {session_id}")
        if workspace_id and session.workspace_id != workspace_id:
            raise AutopilotError("session_not_found", f"Unknown session {session_id}")
        return session
    session = store.active_session_for_project(
        project_id, workspace_id=workspace_id
    )
    if session is None:
        raise AutopilotError("session_not_found", "No active Autopilot session.")
    if workspace_id and session.workspace_id != workspace_id:
        raise AutopilotError("session_not_found", "No active Autopilot session.")
    return session


def headless_driver_tick(
    *,
    project_id: str,
    session_id: str | None = None,
    variable: str = "probe_mutation",
    smoke_ok: bool = True,
    fold0_delta: float = 0.001,
    max_spearman_to_pool: float = 0.5,
    cv_delta: float | None = None,
    integrity_ok: bool = True,
    llm_cost_micros: int = 0,
    store: InMemoryAutopilotStore | None = None,
    local_runner_hook: bool = True,
    night_shift_enabled: bool = True,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """One headless loop step (local runner hook; cloud via fair-share enqueue).

        UCT select → lever_verifier gate → spawn child → successive-halving
        evaluations through available rungs. Never queues Kaggle submit.
        """
    _require_night_shift(night_shift_enabled)
    store = store or get_autopilot_store()
    session = _resolve_session(
        store, project_id, session_id, workspace_id=workspace_id
    )
    if session.status != "running":
        raise AutopilotError("not_running", f"Session status={session.status}")
    if not budget_remaining(session):
        session.status = "completed"
        session.updated_at = datetime.now(UTC)
        _release_lock(store, session.workspace_id, project_id, session.id)
        board = render_morning_digest_ascii(session, store.nodes_for_session(session.id))
        return {
            "status": "completed",
            "reason": "budget_exhausted",
            "session_id": session.id,
            "session": session.to_dict(),
            "ascii_board": board,
            "auto_kaggle_submit": False,
            "lock_released": True,
        }

    nodes = store.nodes_for_session(session.id)
    parent_sel = select_next_parent_node_uct(nodes, mode=session.mode)
    if parent_sel is None:
        raise AutopilotError("no_expandable_parent", "UCT found no expandable parent.")

    gate = gate_mutation(
        variable=variable,
        parent_node_id=parent_sel.node_id,
        mode=session.mode,
    )
    if not gate.allowed:
        raise AutopilotError("lever_verifier_rejected", gate.reason, verifier=gate.status)

    parent = store.nodes[parent_sel.node_id]
    now = datetime.now(UTC)
    child_id = new_autopilot_node_id()
    delta = float(fold0_delta if cv_delta is None else cv_delta)
    child = AutopilotNode(
        id=child_id,
        session_id=session.id,
        parent_id=parent.id,
        rung=0,
        visits=0,
        status="running",
        variable=variable,
        cv_delta=delta,
        cv_std=max(0.01, abs(delta) * 0.5 + 0.01),
        fold0_delta=fold0_delta,
        max_spearman_to_pool=max_spearman_to_pool,
        smoke_ok=None,
        worktree=f".worktrees/autopilot-{child_id}" if local_runner_hook else None,
        created_at=now,
        updated_at=now,
    )
    store.nodes[child_id] = child
    parent.visits += 1
    parent.updated_at = now
    session.probes_launched += 1
    session.spent_llm_cost_micros += int(llm_cost_micros)

    # R0
    child.smoke_ok = smoke_ok
    d0 = evaluate_successive_halving_rung(rung=0, smoke_ok=smoke_ok)
    decisions = [d0]
    if d0.action == "prune":
        child.status = "dead_end"
        child.rung = 0
        session.r0_fail += 1
    elif d0.action == "advance":
        session.r0_pass += 1
        child.rung = 1
        # R1
        d1 = evaluate_successive_halving_rung(
            rung=1,
            fold0_delta=fold0_delta,
            max_spearman_to_pool=max_spearman_to_pool,
        )
        decisions.append(d1)
        if d1.action == "advance":
            session.r1_advance += 1
            apply_r1_stagnation(session, advanced=True)
            child.rung = 2
            child.status = "advanced"
            # R2
            d2 = evaluate_successive_halving_rung(
                rung=2,
                cv_delta=delta,
                integrity_ok=integrity_ok,
            )
            decisions.append(d2)
            if d2.action == "promote":
                child.status = "promoted"
                session.r2_promote += 1
                session.best_node_id = child.id
            elif d2.action == "prune":
                child.status = "pruned"
            else:
                child.status = "running"
        else:
            session.r1_prune += 1
            apply_r1_stagnation(session, advanced=False)
            child.status = "pruned"
    child.visits = 1
    child.updated_at = now
    session.updated_at = now

    return {
        "status": session.status,
        "session_id": session.id,
        "parent_id": parent.id,
        "uct": asdict(parent_sel),
        "child": child.to_dict(),
        "halving": [asdict(d) for d in decisions],
        "lever_verifier": {
            "allowed": gate.allowed,
            "status": gate.status,
            "reason": gate.reason,
            "deferred_to_llm": gate.deferred_to_llm,
        },
        "local_runner_hook": local_runner_hook,
        "auto_kaggle_submit": False,
        "feature_flag": FEATURE_FLAG,
        "notes": list(session.notes[-5:]),
    }


PROBE_LEASE_SECONDS = 15 * 60


def get_next_autopilot_probe(
    *,
    project_id: str,
    workspace_id: str,
    store: InMemoryAutopilotStore | None = None,
) -> dict[str, Any]:
    """Driver B: ~15m lease + fencing token for the next probe."""
    store = store or get_autopilot_store()
    session = _resolve_session(store, project_id, None, workspace_id=workspace_id)
    if session.status != "running":
        raise AutopilotError("not_running", f"Session status={session.status}")
    token = int(session.probes_launched) + 1
    return {
        "session_id": session.id,
        "lease_seconds": PROBE_LEASE_SECONDS,
        "fencing_token": token,
        "template_id": "fold0_smoke",
        "args": {"project_id": project_id},
        "auto_kaggle_submit": False,
    }


def complete_autopilot_rung(
    *,
    project_id: str,
    workspace_id: str,
    session_id: str,
    fencing_token: int,
    variable: str,
    smoke_ok: bool = True,
    store: InMemoryAutopilotStore | None = None,
) -> dict[str, Any]:
    store = store or get_autopilot_store()
    session = _resolve_session(
        store, project_id, session_id, workspace_id=workspace_id
    )
    expected = int(session.probes_launched) + 1
    if fencing_token != expected:
        raise AutopilotError(
            "stale_fence",
            f"expected fencing_token={expected}",
        )
    return headless_driver_tick(
        project_id=project_id,
        session_id=session_id,
        workspace_id=workspace_id,
        variable=variable,
        smoke_ok=smoke_ok,
        store=store,
        night_shift_enabled=True,
    )


# Back-compat for older phase-C stub tests.
def start_autopilot_stub(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Delegate to :func:`start_autopilot`."""
    return start_autopilot(*args, **kwargs)
