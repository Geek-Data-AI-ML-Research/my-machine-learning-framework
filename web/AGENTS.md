# Web UI (`web/`)

ascii.rest terminal campaign console. Existing `site/` stays marketing; SaaS UI lives here.

## Agent setup

Install the ascii skill before editing UI:

```bash
npx skills add bas3line/ascii
```

Pin ascii.rest v0.4+. Bundle pieces for offline Compose.

## Five golden laws

1. **Text `<pre>` vs canvas:** text/ui/data/type/uncolored Banner → `<pre>` with `line-height: 1.2; margin: 0; font-variant-ligatures: none`. Logos/scenes → canvas; always **`mono`** inside workspace. Include ascii.rest **3 KB box-drawing** font fallback.
2. **Motion = Active State:** animate only while running/syncing/transitioning; settle with `fps={0}` or static kit readout. No looping matrix-rain / doom-fire / marquee on data screens.
3. **Compact banners:** secondary headers `<Banner font="slim" pixel={1} max={60} />`.
4. **Live data via `ascii.rest/kit`:** `gauge` / `sparkline` / `progressBar` / `barChart` / `grid` / `glint` — not `pieces` demo loops. Hex only (`THEME_HEX`); no CSS vars / `#fff` / named colors in piece props.
5. **One inverted-ink CTA** per screen; secondary actions as bracketed plain text. Fixed `:` command bar; j/k row cursor.
6. **Primary nav = 6 modes (hotkeys 1–6):** BRAIN / GOALS / LAB / KAGGLE / OPS / TRUST — never 12 horizontal tabs at 88ch.

## DO

- Keep OpenAPI + generated TS types in lockstep with `contracts/openapi.json`.
- Dev persona switcher only when `MYMLFW_ENV=dev`.
- SSE with `Last-Event-ID` when live strips land.

## DO NOT

- Do **not** replace ascii.rest with Tailwind UI / Chart.js / Material.
- Do **not** animate idle dashboards (`matrix-rain`, looping fireworks, marquee on Overview).
- Do **not** invent JSON field names — extend `schemas.py` + regenerate OpenAPI first.
- Do **not** put JWT/PAT in SSE query strings.

## Wave 1

Thin monospace / ascii.rest shell for `/login` + `/studio` + DEV persona switcher stub. Full mode map lands Phase B+.
