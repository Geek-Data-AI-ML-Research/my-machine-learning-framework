/**
 * ascii.rest kit mounts for Studio Overview + New project tutorial.
 * Motion = Active State: still values (fps 0) unless `live` is true.
 */
import { mount } from "ascii.rest";
import { banner } from "ascii.rest/banner";
import { barChart, card, grid, panel, progressBar } from "ascii.rest/kit";

const THEME = {
  fg: "#c8c8c8",
  accent: "#e6e6e6",
  mute: "#6e6e6e",
  ok: "#3fb950",
  warn: "#d29922",
};

const unmounts = new WeakMap();

function clearMount(el) {
  const prev = unmounts.get(el);
  if (typeof prev === "function") {
    try {
      prev();
    } catch (_) {
      /* ignore */
    }
  }
  unmounts.delete(el);
  el.replaceChildren();
}

function attach(el, piece, { live = false } = {}) {
  clearMount(el);
  const stop = mount(el, piece, live ? { fps: 8 } : { fps: 0 });
  unmounts.set(el, stop);
  return stop;
}

function clamp01(n) {
  const x = Number(n);
  if (!Number.isFinite(x)) return 0;
  if (x < 0) return 0;
  if (x > 1) return x > 1 && x <= 100 ? x / 100 : 1;
  return x;
}

function fmt(n, digits = 3) {
  if (n == null || n === "") return "—";
  const x = Number(n);
  if (!Number.isFinite(x)) return "—";
  return x.toFixed(digits);
}

/**
 * Clear Overview board: one progress bar + three metric cards.
 * @param {HTMLElement} el
 * @param {object} dash
 * @param {{ live?: boolean, kind?: string }} [opts]
 */
export function mountOverviewBoard(el, dash, opts = {}) {
  if (!el) return () => {};
  const h = (dash && dash.header) || {};
  const scores = (dash && dash.scores) || {};
  const levers = (dash && dash.levers) || {};
  const missions = (dash && dash.missions) || {};
  const dead = (dash && dash.dead_ends) || {};
  const kaggle = (dash && dash.kaggle) || {};
  const progress = clamp01(h.progress_pct);
  const publicScore =
    scores.best_public != null ? scores.best_public : kaggle.public_score;
  const isKaggle = opts.kind === "kaggle" || Boolean(kaggle.linked);

  const goalCard = card({
    title: "GOAL",
    text: [
      String(h.primary_goal_title || "no primary goal").slice(0, 34),
      `thr ${fmt(h.primary_threshold)}   now ${fmt(h.primary_latest)}`,
      `gap ${fmt(h.primary_gap)}   ${h.primary_status || "OPEN"}`,
    ].join("\n"),
    footer: `${(progress * 100).toFixed(0)}% campaign`,
    width: 38,
    color: THEME.accent,
  });

  const scoreCard = card({
    title: "SCORE",
    text: isKaggle
      ? [
          `public  ${fmt(publicScore)}`,
          `rank    ${kaggle.rank ?? "—"}`,
          `best cv ${fmt(scores.best_cv)}`,
        ].join("\n")
      : [`best cv ${fmt(scores.best_cv)}`, "public  —", "standalone"].join("\n"),
    footer: isKaggle ? "kaggle public LB" : "notebook",
    width: 38,
    color: THEME.ok,
  });

  const workCard = card({
    title: "WORK",
    text: [
      `levers    ${(levers.open || 0)} open / ${(levers.closed || 0)} closed`,
      `missions  ${(missions.queued || 0)}q ${(missions.running || 0)}run ${(missions.succeeded || 0)}ok`,
      `dead ends ${(dead.count || 0)}`,
    ].join("\n"),
    footer: "0.5 G + 0.3 L + 0.2 M",
    width: 38,
    color: THEME.warn,
  });

  const board = grid(
    [
      progressBar({
        value: progress,
        label: "progress",
        width: 52,
        style: "blocks",
        color: THEME.accent,
      }),
      goalCard,
      scoreCard,
      workCard,
    ],
    { columns: 3, gap: 2, border: false, name: "studio-overview" }
  );

  return attach(el, board, { live: Boolean(opts.live) });
}

const WIZARD_COPY = {
  kind: [
    "Pick a real campaign name (slug follows).",
    "kaggle → competition workspace + Kaggle mode.",
    "standalone → notebook / research only.",
    "Do not invent a Demo Campaign.",
  ],
  goals: [
    "One measurable primary goal is required.",
    "kaggle → kind kaggle_public, metric public_score.",
    "standalone → kind notebook_score, metric cv_mean.",
    "Threshold is the bar you must beat — be honest.",
  ],
  link: [
    "Kaggle: paste the competition slug exactly.",
    "Example: playground-series-s6e11",
    "Seal API token later under Kaggle → token.",
    "Git remote optional; link from Ops later.",
  ],
  review: [
    "Create stores the project in Mongo (org-scoped).",
    "Next: Overview → Sync Kaggle if linked.",
    "Then Lab for levers; never auto-submit overnight.",
    "Progress = 0.5·goals + 0.3·levers + 0.2·missions.",
  ],
};

/**
 * @param {HTMLElement} el
 * @param {string} stepName
 * @param {{ kind?: string, name?: string }} [ctx]
 */
export function mountWizardTutorial(el, stepName, ctx = {}) {
  if (!el) return () => {};
  const lines = WIZARD_COPY[stepName] || WIZARD_COPY.kind;
  const kind = ctx.kind === "kaggle" ? "kaggle" : "standalone";
  const head = banner("new project", {
    font: "slim",
    shadow: "none",
    fill: "#",
    color: [THEME.accent, THEME.mute],
    effect: "still",
  });
  const tip = panel(lines.join("\n"), {
    title: `${stepName} · ${kind}`,
    cols: 56,
    rows: 8,
    color: THEME.fg,
  });
  const checklist = barChart(
    {
      name: ctx.name ? 1 : 0,
      goal: stepName === "kind" ? 0 : 1,
      link: ["link", "review"].includes(stepName) ? 1 : 0,
      go: stepName === "review" ? 1 : 0,
    },
    { color: THEME.ok }
  );
  const board = grid([head, tip, checklist], {
    columns: 1,
    gap: 1,
    border: { title: true },
    name: "wizard-guide",
  });
  return attach(el, board, { live: false });
}

export function unmountAscii(el) {
  if (el) clearMount(el);
}

export { THEME };
