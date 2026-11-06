# Web UI (`web/`)

Campaign SaaS Studio console. Existing `site/` stays marketing; SaaS UI lives here.

## Stack (binding)

Preferred, current design system:

- **Tailwind CSS** (utility layout, typography, spacing, dark theme)
- **[Charts.css](https://github.com/ChartsCSS/charts.css)** for pure-HTML/CSS metric charts (bars, lines, progress) — no Chart.js / heavy canvas chart libs unless a screen truly needs them
- Semantic HTML first; progressive enhancement for interactivity in `public/` (or a later Vite/React layer if introduced)

Studio is **not** tied to ascii.rest. Do not add ascii.rest kit / Banner / terminal pieces as the default UI.

## UX laws

1. **Readable dashboard:** Overview shows only important metrics (progress, public/CV score, rank when kaggle, open work). No metric walls.
2. **Motion = Active State:** animate only while running/syncing/transitioning. No looping decorative motion on idle Overview.
3. **One primary CTA** per screen; secondary actions as text/ghost controls.
4. **Primary nav = 6 modes (hotkeys 1–6):** BRAIN / GOALS / LAB / KAGGLE / OPS / TRUST — keep Dead ends / Submissions as nested surfaces under Goals/Lab/Kaggle when needed, not a 12-tab top bar.
5. **Accessible contrast** on the dark Studio theme; prefer CSS variables mapped through Tailwind theme tokens.

## DO

- Keep OpenAPI + generated TS types in lockstep with `contracts/openapi.json`.
- Dev persona switcher only when `MYMLFW_ENV=dev`.
- SSE with `Last-Event-ID` when live strips land.
- Vendor or build Tailwind + Charts.css for offline Compose (`deploy/Dockerfile.web`).

## DO NOT

- Do **not** rebuild Studio on ascii.rest / monospace kit boards as the design system.
- Do **not** invent JSON field names — extend `schemas.py` + regenerate OpenAPI first.
- Do **not** put JWT/PAT in SSE query strings.
- Do **not** animate idle dashboards.

## Migration note

Legacy `public/app.js` may still contain ascii.rest mounts (`vendor/mymlfw-ascii.js`). New UI work should migrate screens to Tailwind + Charts.css and remove ascii hosts when each screen is rewritten.
