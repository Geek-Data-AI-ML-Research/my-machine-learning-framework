/* Studio console — Tailwind CSS + Charts.css (see web/AGENTS.md). */
(function () {
  // Compose maps API→8001 / web→5175; empty base when page is served from the API port.
  const API = (
    window.MYMLFW_API ||
    (location.port === "8000" || location.port === "8001" ? "" : "http://127.0.0.1:8001")
  ).replace(/\/$/, "");
  const app = document.getElementById("app");
  const state = {
    route: location.hash.replace(/^#/, "") || "login",
    token: localStorage.getItem("mymlfw_token") || "",
    me: null,
    projects: [],
    dashboard: null,
    projectId: null,
    paletteOpen: false,
    paletteQuery: "",
    mode: "BRAIN",
    row: 0,
    error: "",
    trainStrip: null,
    sse: null,
    nightDigest: null,
    loginStep: "email",
    loginMode: "sign-in",
    loginEmail: "",
    boards: {},
    filter: "all",
    search: "",
    notice: "",
    advise: null,
    intel: null,
    autopilot: null,
    accounts: null,
    wizard: null,
    playbookCatalog: null,
    playbookCatalogKey: "",
    playbookCatalogLoading: false,
    settings: null,
    inviteFor: null,
    inviteEmail: "",
    goalsList: null,
    sourcesList: null,
    roadmapList: null,
    roadmapFilter: "all",
    roadmapSummaryOpen: false,
    gitInfo: null,
    progressNotes: null,
    deadEndsList: null,
    deadEndsFilter: "all",
    leversList: null,
    missionsList: null,
    members: null,
    runners: null,
    gpus: null,
    quote: null,
    gitPlan: null,
    researchLast: null,
    ensembleLast: null,
    creditsBoard: null,
    modeDataFor: null,
  };

  function pid() {
    return state.projectId;
  }

  async function refreshDashboard() {
    if (!state.projectId) return;
    state.boards[state.projectId] = await api("/v1/projects/" + state.projectId + "/dashboard");
    state.dashboard = state.boards[state.projectId];
  }

  async function loadModeData(force) {
    const projectId = state.projectId;
    if (!projectId) return;
    const key = projectId + ":" + state.mode;
    if (!force && state.modeDataFor === key) return;
    const project = currentProject();
    try {
      if (state.mode === "BRAIN") {
        const [progress, dead, levers, missions, roadmap] = await Promise.all([
          api("/v1/projects/" + projectId + "/progress"),
          api("/v1/projects/" + projectId + "/dead-ends"),
          api("/v1/projects/" + projectId + "/levers"),
          api("/v1/projects/" + projectId + "/missions"),
          api("/v1/projects/" + projectId + "/roadmap"),
        ]);
        state.progressNotes = progress.notes || [];
        state.deadEndsList = dead.dead_ends || [];
        state.leversList = levers.levers || [];
        state.missionsList = missions.missions || [];
        state.roadmapList = roadmap.strategies || [];
      } else if (state.mode === "GOALS") {
        const goals = await api("/v1/projects/" + projectId + "/goals");
        state.goalsList = goals.goals || [];
      } else if (state.mode === "DEAD_ENDS") {
        const dead = await api("/v1/projects/" + projectId + "/dead-ends");
        state.deadEndsList = dead.dead_ends || [];
      } else if (state.mode === "SOURCES") {
        const sources = await api("/v1/projects/" + projectId + "/sources");
        state.sourcesList = sources.sources || [];
      } else if (state.mode === "ROADMAP") {
        const [roadmap, dead] = await Promise.all([
          api("/v1/projects/" + projectId + "/roadmap"),
          api("/v1/projects/" + projectId + "/dead-ends"),
        ]);
        state.roadmapList = roadmap.strategies || [];
        state.deadEndsList = dead.dead_ends || [];
      } else if (state.mode === "GIT") {
        state.gitInfo = await api("/v1/projects/" + projectId + "/git");
      } else if (state.mode === "LAB") {
        const [levers, ap] = await Promise.all([
          api("/v1/projects/" + projectId + "/levers"),
          api("/v1/projects/" + projectId + "/autopilot/status").catch((e) => ({
            message: String(e.message || e),
          })),
        ]);
        state.leversList = levers.levers || [];
        state.autopilot = ap;
        state.autopilotFor = projectId;
      } else if (state.mode === "KAGGLE" && project && project.kind === "kaggle") {
        state.intel = await api("/v1/projects/" + projectId + "/kaggle/intel");
        state.intelFor = projectId;
      } else if (state.mode === "OPS") {
        const [accounts, runners, gaps] = await Promise.all([
          api("/v1/orgs/current/cloud/accounts").catch((e) => ({ error: String(e.message || e) })),
          api("/v1/orgs/current/runners").catch((e) => ({ error: String(e.message || e) })),
          api("/v1/orgs/current/mcp-gaps").catch(() => ({ gaps: [] })),
        ]);
        state.accounts = accounts;
        state.runners = runners;
        state.mcpGaps = gaps.gaps || [];
        state.accountsFor = projectId;
      } else if (state.mode === "TRUST") {
        const members = await api("/v1/projects/" + projectId + "/members");
        state.members = members.members || [];
      }
      state.modeDataFor = key;
    } catch (e) {
      state.error = String(e.message || e);
    }
  }

  function connectTrainStrip() {
    if (!state.token || state.sse) return;
    try {
      // Cookie/bearer via fetch EventSource polyfill is Phase A+; hook uses fetch stream later.
      // For now poll /v1/events once to surface kit train_strip shape (Motion = Active State).
      fetch(API + "/v1/events", {
        headers: {
          Authorization: "Bearer " + state.token,
          "X-Mymlfw-Client-Version": "0.1.0",
          Accept: "text/event-stream",
        },
      })
        .then((res) => res.text())
        .then((text) => {
          const match = text.match(/event: train_strip\ndata: (.+)\n/);
          if (match) {
            try {
              state.trainStrip = JSON.parse(match[1]);
              if (state.route.startsWith("studio")) render();
            } catch (_) {}
          }
        })
        .catch(() => {});
      state.sse = true;
    } catch (_) {}
  }

  function setRoute(route) {
    state.route = route;
    location.hash = route;
    render();
  }

  async function api(path, opts = {}) {
    const headers = Object.assign(
      { "Content-Type": "application/json", "X-Mymlfw-Client-Version": "0.1.0" },
      opts.headers || {}
    );
    if (state.token) headers.Authorization = "Bearer " + state.token;
    const method = String(opts.method || "GET").toUpperCase();
    if (method !== "GET" && method !== "HEAD" && !headers["Idempotency-Key"]) {
      headers["Idempotency-Key"] = "web-" + Date.now().toString(36) + "-" + Math.random().toString(16).slice(2);
    }
    const res = await fetch(API + path, Object.assign({}, opts, { headers }));
    const text = await res.text();
    let body = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch (_) {
      body = { raw: text };
    }
    if (!res.ok) {
      const detail = body && body.detail;
      const msg =
        (body && body.message) ||
        (typeof detail === "string" ? detail : detail && (detail.message || detail.error_code)) ||
        (body && body.error_code) ||
        res.statusText;
      throw new Error(String(msg));
    }
    return body;
  }

  async function afterAuth(tok) {
    state.token = tok.access_token;
    localStorage.setItem("mymlfw_token", state.token);
    state.me = await api("/v1/me");
    setRoute("studio");
  }

  async function login(email, password) {
    const tok = await api("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    await afterAuth(tok);
  }

  async function register(email, password, display_name) {
    const tok = await api("/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, display_name }),
    });
    await afterAuth(tok);
  }

  async function switchPersona(persona) {
    state.me = await api("/v1/dev/persona", {
      method: "POST",
      body: JSON.stringify({ persona }),
    });
    render();
  }

  async function loadStudio() {
    const list = await api("/v1/projects");
    state.projects = list.projects || [];
    await Promise.all(
      state.projects.map(async (project) => {
        try {
          state.boards[project.id] = await api("/v1/projects/" + project.id + "/dashboard");
        } catch (_) {}
      })
    );
  }

  function fmtPct(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    const shown = Math.abs(n) <= 1 ? n * 100 : n;
    return shown.toFixed(1) + "%";
  }

  function fmtNum(value, digits) {
    if (value == null || value === "") return "—";
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return n.toFixed(digits == null ? 3 : digits);
  }

  function ratio01(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return 0;
    if (n < 0) return 0;
    if (n <= 1) return n;
    if (n <= 100) return n / 100;
    return 1;
  }

  function chartsBarRows(rows) {
    return `
<table class="charts-css bar show-labels data-spacing-4 reverse-data show-primary-axis">
  <tbody>
    ${rows
      .map((row) => {
        const size = Math.max(0, Math.min(1, ratio01(row.size)));
        return `<tr>
      <th scope="row">${escText(row.label)}</th>
      <td style="--size: ${size.toFixed(4)};"><span class="data">${escText(row.display || "")}</span></td>
    </tr>`;
      })
      .join("")}
  </tbody>
</table>`;
  }

  function currentProject() {
    return (state.projects || []).find((p) => p.id === state.projectId) || null;
  }

  function renderPalette() {
    if (!state.paletteOpen) return "";
    const cmds = [
      { key: "brain", label: "1 brain — Overview" },
      { key: "goals", label: "2 goals" },
      { key: "lab", label: "3 lab — Research / Ensemble / Night" },
      { key: "night", label: "3 night — Night-Shift Autopilot digest" },
      { key: "share", label: "share — publish public snapshot" },
      { key: "studio", label: "studio — project list" },
    ].filter((c) => !state.paletteQuery || c.label.includes(state.paletteQuery.toLowerCase()));
    return `
<div class="palette" id="palette">
  <input id="palette-input" placeholder="Jump to…" value="${state.paletteQuery.replace(/"/g, "&quot;")}" />
  <ul class="palette-list">
    ${cmds.map((c) => `<li data-cmd="${c.key}">${c.label}</li>`).join("")}
  </ul>
</div>`;
  }

  function bindPalette() {
    const root = document.getElementById("palette");
    if (!root) return;
    const input = document.getElementById("palette-input");
    if (input) {
      input.focus();
      input.oninput = () => {
        state.paletteQuery = input.value;
        render();
      };
    }
    root.querySelectorAll("[data-cmd]").forEach((el) => {
      el.onclick = async () => {
        const cmd = el.getAttribute("data-cmd");
        state.paletteOpen = false;
        state.paletteQuery = "";
        if (cmd === "share" && state.projectId) {
          try {
            const snap = await api("/v1/projects/" + state.projectId + "/share", {
              method: "POST",
              body: JSON.stringify({
                include_goals: true,
                include_lever_stats: true,
                include_dead_end_lessons: false,
              }),
            });
            state.notice = "Published " + snap.share_path;
            state.error = "";
          } catch (e) {
            state.error = String(e.message || e);
          }
          render();
          return;
        }
        if (cmd === "studio") {
          state.projectId = null;
          setRoute("studio");
          return;
        }
        if (state.projectId && (cmd === "brain" || cmd === "goals" || cmd === "lab" || cmd === "night")) {
          const mode = cmd === "night" ? "lab" : cmd;
          state.mode = mode.toUpperCase();
          setRoute("studio/" + state.projectId + "/" + mode);
          return;
        }
        render();
      };
    });
  }

  function showChrome(kind) {
    const banner = document.getElementById("banner");
    if (banner) banner.hidden = true;
    document.body.classList.toggle("login-screen", kind === "login");
    document.body.classList.toggle("studio", kind === "studio");
  }

  function signInError(err) {
    const msg = String((err && err.message) || err || "");
    if (/failed to fetch|network|unsupported method/i.test(msg)) {
      return "could not reach the api";
    }
    return "could not sign in";
  }

  function escText(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function renderLogin() {
    showChrome("login");
    const creating = state.loginMode === "register";
    const email = escText(state.loginEmail);
    const err = escText(state.error || "");
    app.innerHTML = `
<div class="flex min-h-screen items-center justify-center px-4">
  <div class="w-full max-w-sm">
    <p class="studio-brand mb-3">MYMLFW</p>
    <h1 class="mb-6 text-2xl font-semibold tracking-tight text-signal">${creating ? "Create account" : "Sign in"}</h1>
    <form id="login-form" class="space-y-1">
      <label class="studio-label" for="email">Email</label>
      <input class="studio-input" id="email" name="username" type="email" inputmode="email" autocomplete="username" spellcheck="false" value="${email}" />
      <label class="studio-label" for="password">Password</label>
      <input class="studio-input" id="password" name="password" type="password" autocomplete="${creating ? "new-password" : "current-password"}" />
      <button class="studio-cta mt-5 w-full" type="submit">${creating ? "Create account" : "Sign in"}</button>
    </form>
    <button type="button" class="studio-link mt-4" id="do-switch">${creating ? "Sign in" : "Create account"}</button>
    <p class="studio-err" id="err">${err}</p>
  </div>
</div>
`;
    const emailEl = document.getElementById("email");
    const passwordEl = document.getElementById("password");
    if (state.error === "enter a password") passwordEl.focus();
    else emailEl.focus();
    document.getElementById("login-form").onsubmit = async (ev) => {
      ev.preventDefault();
      state.loginEmail = emailEl.value.trim();
      state.error = "";
      if (!state.loginEmail) {
        state.error = "enter a login";
        renderLogin();
        return;
      }
      const password = passwordEl.value;
      if (!password) {
        state.error = "enter a password";
        renderLogin();
        return;
      }
      try {
        if (creating) await register(state.loginEmail, password, "Dev");
        else await login(state.loginEmail, password);
      } catch (e) {
        state.error = signInError(e);
        renderLogin();
      }
    };
    document.getElementById("do-switch").onclick = () => {
      state.loginEmail = emailEl.value.trim();
      state.loginMode = creating ? "sign-in" : "register";
      state.error = "";
      renderLogin();
    };
  }

  function shell(title, body, primary) {
    const me = state.me || {};
    const user = me.user || {};
    const org = me.org || {};
    const notice = state.notice ? `<p class="studio-note">${escText(state.notice)}</p>` : "";
    const err = state.error ? `<p class="studio-err">${escText(state.error)}</p>` : "";
    return `
<div class="studio-shell">
  <header class="studio-topbar">
    <button type="button" class="studio-brand" id="go-home">mymlfw</button>
    <span class="text-sm text-mist-400">${escText(title)}</span>
    <span class="ml-auto font-mono text-xs text-mist-500">${escText(user.email || "")} · ${escText(org.slug || "org")} · ${escText(me.persona || "unset")}</span>
    <button type="button" class="studio-ghost" id="go-settings">Settings</button>
    <button type="button" class="studio-ghost" id="logout">Log out</button>
  </header>
  ${state.paletteOpen ? renderPalette() : ""}
  ${notice}${err}
  ${body}
  ${primary || ""}
</div>`;
  }

  function bindShell(extra) {
    document.getElementById("go-home").onclick = () => {
      state.projectId = null;
      state.mode = "BRAIN";
      state.notice = "";
      state.error = "";
      setRoute("studio");
    };
    const settingsBtn = document.getElementById("go-settings");
    if (settingsBtn) {
      settingsBtn.onclick = () => setRoute("settings");
    }
    document.getElementById("logout").onclick = () => {
      state.token = "";
      state.me = null;
      state.dashboard = null;
      state.projects = [];
      state.boards = {};
      state.advise = null;
      state.settings = null;
      localStorage.removeItem("mymlfw_token");
      setRoute("login");
    };
    bindPalette();
    if (extra) extra();
  }

  function filteredProjects() {
    const q = state.filter;
    const needle = (state.search || "").trim().toLowerCase();
    return (state.projects || []).filter((p) => {
      const kindOk =
        q === "all" || p.kind === q || (q === "standalone" && p.kind !== "kaggle");
      if (!kindOk) return false;
      if (!needle) return true;
      const hay = [p.name, p.slug, p.kind].join(" ").toLowerCase();
      return hay.includes(needle);
    });
  }

  function fmtUpdated(value) {
    if (!value) return "—";
    try {
      const d = new Date(value);
      if (Number.isNaN(d.getTime())) return "—";
      return d.toISOString().slice(0, 10);
    } catch (_) {
      return "—";
    }
  }

  function renderHome() {
    showChrome("studio");
    const projects = filteredProjects();
    const rows = projects
      .map((p, i) => {
        const board = state.boards[p.id];
        const h = (board && board.header) || {};
        const levers = (board && board.levers) || {};
        const openLever = Number(levers.open || 0) > 0 ? "yes" : "—";
        const inviteOpen = state.inviteFor === p.id;
        return `<tr class="${i === state.row ? "bg-ink-800" : "hover:bg-ink-900/80"}" data-id="${escText(p.id)}">
          <td class="px-3 py-3"><strong class="text-signal">${escText(p.name || p.slug)}</strong><div class="text-xs text-mist-500">${escText(p.slug)}${p.is_demo ? " · demo" : ""}</div></td>
          <td class="px-3 py-3">${escText(p.kind || "")}</td>
          <td class="px-3 py-3">${escText(h.primary_goal_title || "—")}</td>
          <td class="px-3 py-3">${fmtNum(h.primary_threshold)}<div class="text-xs text-mist-500">${fmtPct(h.progress_pct)}</div></td>
          <td class="px-3 py-3">${openLever}</td>
          <td class="px-3 py-3 font-mono text-xs text-mist-500">${fmtUpdated(p.updated_at)}</td>
          <td class="px-3 py-3">
            <div class="flex flex-wrap gap-2">
              <button type="button" class="studio-ghost open-project" data-id="${escText(p.id)}">Open</button>
              <button type="button" class="studio-ghost share-project" data-id="${escText(p.id)}">Share</button>
              <button type="button" class="studio-ghost invite-project" data-id="${escText(p.id)}">Invite</button>
              <button type="button" class="studio-ghost archive-project" data-id="${escText(p.id)}">Archive</button>
            </div>
            ${inviteOpen ? `<div class="mt-2 flex gap-2"><input type="email" class="studio-input invite-email" placeholder="email" value="${escText(state.inviteEmail)}" /><button type="button" class="studio-ghost send-invite" data-id="${escText(p.id)}">Send</button></div>` : ""}
          </td>
        </tr>`;
      })
      .join("");
    const body = `
<section>
  <div class="mb-6 flex flex-wrap items-end justify-between gap-4">
    <div>
      <h1 class="text-3xl font-semibold tracking-tight text-signal">Projects</h1>
      <p class="mt-1 text-sm text-mist-400">Manage campaigns. New project opens the DS playbook wizard (EDA → CV → baseline).</p>
    </div>
    <button type="button" class="studio-cta" id="new-project">New project</button>
  </div>
  <div class="mb-4 flex flex-wrap items-center gap-2" role="tablist">
    ${["all", "kaggle", "standalone"]
      .map(
        (f) =>
          `<button type="button" class="studio-tab ${state.filter === f ? "studio-tab-on" : ""}" data-filter="${f}">${f}</button>`
      )
      .join("")}
    <input id="project-search" class="studio-input ml-auto max-w-xs" type="search" placeholder="Search slug or name" value="${escText(state.search)}" />
  </div>
  <div class="overflow-x-auto rounded-xl border border-ink-700">
    <table class="min-w-full text-left text-sm">
      <thead class="border-b border-ink-700 bg-ink-900 text-xs uppercase tracking-[0.08em] text-mist-500">
        <tr>
          <th class="px-3 py-2">Project</th><th class="px-3 py-2">Kind</th><th class="px-3 py-2">Primary goal</th>
          <th class="px-3 py-2">Best / progress</th><th class="px-3 py-2">Open lever?</th><th class="px-3 py-2">Updated</th><th class="px-3 py-2"></th>
        </tr>
      </thead>
      <tbody class="divide-y divide-ink-700">${rows || `<tr><td colspan="7" class="px-3 py-8 text-center text-mist-500">No projects in this filter.</td></tr>`}</tbody>
    </table>
  </div>
  <details class="mt-6 rounded-xl border border-ink-700 bg-ink-900 p-3 text-sm">
    <summary class="cursor-pointer text-mist-400">Dev persona</summary>
    <div class="mt-3 flex flex-wrap items-center gap-2">
      <select id="persona" class="studio-input max-w-xs">
        <option value="owner">owner</option>
        <option value="member">member</option>
        <option value="viewer">viewer</option>
        <option value="agent">agent</option>
      </select>
      <button type="button" class="studio-ghost" id="apply-persona">Switch</button>
    </div>
  </details>
</section>`;
    app.innerHTML = shell("Studio", body, "");
    const me = state.me || {};
    if (me.persona) {
      const sel = document.getElementById("persona");
      if (sel) sel.value = me.persona;
    }
    bindShell(() => {
      document.getElementById("new-project").onclick = () => {
        state.wizard = defaultWizard();
        state.error = "";
        setRoute("studio/new");
      };
      document.querySelectorAll("[data-filter]").forEach((el) => {
        el.onclick = () => {
          state.filter = el.getAttribute("data-filter");
          renderHome();
        };
      });
      const search = document.getElementById("project-search");
      if (search) {
        search.oninput = () => {
          state.search = search.value;
          renderHome();
          const again = document.getElementById("project-search");
          if (again) {
            again.focus();
            const len = again.value.length;
            again.setSelectionRange(len, len);
          }
        };
      }
      document.querySelectorAll(".open-project").forEach((el) => {
        el.onclick = (ev) => {
          ev.stopPropagation();
          const id = el.getAttribute("data-id");
          if (!id) return;
          state.notice = "";
          state.error = "";
          state.mode = "BRAIN";
          state.advise = null;
          setRoute("studio/" + id + "/brain");
        };
      });
      document.querySelectorAll(".share-project").forEach((el) => {
        el.onclick = async (ev) => {
          ev.stopPropagation();
          const id = el.getAttribute("data-id");
          try {
            const snap = await api("/v1/projects/" + id + "/share", {
              method: "POST",
              body: JSON.stringify({
                include_goals: true,
                include_lever_stats: true,
                include_dead_end_lessons: false,
              }),
            });
            state.notice = "Published " + snap.share_path;
            state.error = "";
            renderHome();
          } catch (e) {
            state.error = String(e.message || e);
            renderHome();
          }
        };
      });
      document.querySelectorAll(".invite-project").forEach((el) => {
        el.onclick = (ev) => {
          ev.stopPropagation();
          const id = el.getAttribute("data-id");
          state.inviteFor = state.inviteFor === id ? null : id;
          state.inviteEmail = "";
          renderHome();
        };
      });
      document.querySelectorAll(".send-invite").forEach((el) => {
        el.onclick = async (ev) => {
          ev.stopPropagation();
          const id = el.getAttribute("data-id");
          const input = el.parentElement && el.parentElement.querySelector(".invite-email");
          const email = (input && input.value) || state.inviteEmail;
          try {
            await api("/v1/projects/" + id + "/invite", {
              method: "POST",
              body: JSON.stringify({ email, role: "member" }),
            });
            state.notice = "Invited " + email;
            state.inviteFor = null;
            state.error = "";
            renderHome();
          } catch (e) {
            state.error = String(e.message || e);
            renderHome();
          }
        };
      });
      document.querySelectorAll(".archive-project").forEach((el) => {
        el.onclick = async (ev) => {
          ev.stopPropagation();
          const id = el.getAttribute("data-id");
          try {
            await api("/v1/projects/" + id + "/archive", { method: "POST", body: "{}" });
            state.notice = "Archived project";
            state.error = "";
            await loadStudio();
            renderHome();
          } catch (e) {
            state.error = String(e.message || e);
            renderHome();
          }
        };
      });
      const apply = document.getElementById("apply-persona");
      if (apply) {
        apply.onclick = async () => {
          try {
            await switchPersona(document.getElementById("persona").value);
          } catch (e) {
            state.error = String(e.message || e);
            renderHome();
          }
        };
      }
    });
  }

  function defaultWizard() {
    return {
      step: 0,
      name: "",
      kind: "standalone",
      modality: "tabular",
      validation: "time_group",
      baseline: "lightgbm",
      threshold: "0.30",
      paradigmShifts: [],
      kaggle: "",
      git: "",
      seedRoadmap: true,
    };
  }

  function wizardSteps() {
    return ["venue", "modality", "validation", "baseline", "strategies", "link", "review"];
  }

  function wizardStepMeta(id) {
    const map = {
      venue: { label: "Venue", title: "Name the campaign & pick the venue" },
      modality: { label: "Data", title: "What does the data look like?" },
      validation: { label: "CV", title: "Lock a leak-free validation split" },
      baseline: { label: "Baseline", title: "Start with a fast dumb baseline" },
      strategies: { label: "Strategies", title: "Modality ladder & paradigm shifts" },
      link: { label: "Links", title: "Connect competition or git" },
      review: { label: "Create", title: "Review playbook & create" },
    };
    return map[id] || { label: id, title: id };
  }

  /** Shared with ``python -m mymlfw playbook`` via GET /v1/playbook/catalog. */
  async function ensurePlaybookCatalog(w, force) {
    const modality = (w && w.modality) || "tabular";
    const kind = (w && w.kind) || "standalone";
    const key = modality + "|" + kind;
    if (!force && state.playbookCatalog && state.playbookCatalogKey === key) {
      return state.playbookCatalog;
    }
    const cat = await api(
      "/v1/playbook/catalog?modality=" +
        encodeURIComponent(modality) +
        "&kind=" +
        encodeURIComponent(kind)
    );
    state.playbookCatalog = cat;
    state.playbookCatalogKey = key;
    return cat;
  }

  function modalityStrategyCatalog(modality) {
    const cat = state.playbookCatalog;
    if (cat && cat.strategies_by_modality && cat.strategies_by_modality[modality]) {
      return cat.strategies_by_modality[modality];
    }
    if (cat && cat.modality === modality && Array.isArray(cat.strategies)) {
      return cat.strategies;
    }
    return [];
  }

  function paradigmShiftCatalog(w) {
    const cat = state.playbookCatalog;
    const venue = w.kind === "kaggle" ? "kaggle" : "standalone";
    const source =
      cat && Array.isArray(cat.all_paradigm_shifts)
        ? cat.all_paradigm_shifts
        : cat && Array.isArray(cat.paradigm_shifts)
          ? cat.paradigm_shifts
          : [];
    return source.filter((s) => {
      const venues = s.venues || [];
      if (venues.length && venues.indexOf(venue) < 0) return false;
      const when = s.when || "any";
      if (when !== "any" && when !== w.modality) return false;
      return true;
    });
  }

  function wizardCoach(w, stepName) {
    const coaches = {
      venue:
        "Never start by picking a model. First 60% of Kaggle and commercial work is identical: EDA → lock CV → dumb baseline → domain features. The last 40% diverges (LB squeeze vs ROI/latency).",
      modality:
        "Match modality to model family later — not now. Tabular → trees + linear. Text/docs → transformers. Vision → pretrained backbones. Sequences → rolling aggregates first, then a small sequence model if needed.",
      validation:
        w.kind === "kaggle"
          ? "Static / synthetic contests: StratifiedKFold (often 5 folds) so each fold mirrors the target rate. Treat this as the yardstick before any feature or model claim."
          : "Live commercial data: prefer time-based holdout plus group splits (same customer/entity stays in one split) so you never peek into the future.",
      baseline:
        "Run an out-of-the-box LightGBM / Logistic / XGB on raw features on CPU (15–60s). You get a score to beat and a feature-importance leak alarm (e.g. 0.99 importance on one column).",
      strategies:
        "The ladder is ordered: default → escalate → paradigm. Tick only paradigm shifts that might apply later — they seed optional roadmap items after Stages 1–5, never replace EDA/CV/baseline.",
      link:
        w.kind === "kaggle"
          ? "Paste the exact competition slug from the Kaggle URL. Seal API tokens later under Kaggle — never in the project name."
          : "Git is optional at create time. Link from Ops when the repo exists.",
      review:
        "Create writes the project under your org and seeds Stages 1–5 (+ selected paradigm shifts) on the Roadmap so agents start with EDA, not GPT.",
    };
    return coaches[stepName] || "";
  }

  function wizardChoice(name, value, selected, title, hint) {
    const on = selected === value;
    return `<label class="flex cursor-pointer gap-3 rounded-xl border p-3 transition ${
      on
        ? "border-signal/50 bg-signal/10"
        : "border-ink-700 bg-ink-950/40 hover:border-ink-500"
    }">
      <input type="radio" class="mt-1" name="${escText(name)}" value="${escText(value)}" ${on ? "checked" : ""} />
      <span class="min-w-0">
        <span class="block text-sm font-medium text-signal">${escText(title)}</span>
        <span class="mt-0.5 block text-xs leading-relaxed text-mist-400">${escText(hint)}</span>
      </span>
    </label>`;
  }

  function applyVenueDefaults(w) {
    if (w.kind === "kaggle") {
      if (!w.validation || w.validation === "time_group") w.validation = "skf5";
      if (!w.threshold || w.threshold === "0.30") w.threshold = "0.70";
    } else {
      if (!w.validation || w.validation === "skf5") w.validation = "time_group";
      if (!w.threshold || w.threshold === "0.70") w.threshold = "0.30";
    }
    if (w.modality === "tabular" && !w.baseline) w.baseline = "lightgbm";
    if (w.modality === "text") w.baseline = w.baseline || "logistic";
    if (w.modality === "vision") w.baseline = "lightgbm";
    if (w.modality === "sequential") w.baseline = "lightgbm";
  }

  function playbookLabels(w) {
    const modality = {
      tabular: "Structured tabular",
      text: "Text / documents",
      vision: "Images / video / audio",
      sequential: "Sequential events",
    };
    const validation = {
      skf5: "5-fold StratifiedKFold",
      time_group: "Time holdout + group split",
      group_kfold: "GroupKFold (entity-safe)",
    };
    const baseline = {
      lightgbm: "LightGBM (default trees)",
      logistic: "Logistic / Ridge",
      xgboost: "XGBoost",
      catboost: "CatBoost",
    };
    const shifts = paradigmShiftCatalog(w).filter(
      (s) => (w.paradigmShifts || []).indexOf(s.id) >= 0
    );
    return {
      venue: w.kind === "kaggle" ? "Kaggle competition" : "Commercial / standalone",
      modality: modality[w.modality] || w.modality,
      validation: validation[w.validation] || w.validation,
      baseline: baseline[w.baseline] || w.baseline,
      shifts: shifts,
      strategies: modalityStrategyCatalog(w.modality),
    };
  }

  function strategyLadderPlan(w) {
    const ladder = modalityStrategyCatalog(w.modality);
    return ladder
      .map((s) => `• [${s.tier}] ${s.title} — ${s.detail}`)
      .join("\n");
  }

  function buildPlaybookRoadmap(w) {
    const labels = playbookLabels(w);
    const isKaggle = w.kind === "kaggle";
    const baselinePlan =
      w.modality === "text"
        ? `After EDA + CV lock: start with a fast linear/logistic or embedding + linear baseline before heavy LLMs. Preferred starter: ${labels.baseline}. Only escalate to DeBERTa / open-weight LLMs if text columns carry the signal.`
        : w.modality === "vision"
          ? `After EDA + CV lock: extract pretrained backbone embeddings (ConvNeXt / ViT) and train a linear/LightGBM head before fine-tuning a heavy net. Starter track: ${labels.baseline} on frozen features.`
          : w.modality === "sequential"
            ? `After EDA + CV lock: build rolling-window aggregates (count_last_24h, mean_last_7d) and beat them with ${labels.baseline}. Only then test a small GRU / lightweight Transformer if you have millions of sequences.`
            : `Run out-of-the-box ${labels.baseline} on raw features (CPU, ~15–60s). Record OOF score + feature importances. A single column with ~0.99 importance is a leakage alarm — stop and fix CV/features.`;
    const items = [
      {
        title: "Stage 1 — EDA & data hygiene",
        priority: 10,
        plan: `Inspect shape, dtypes, target rate, missingness, outliers, and corrupted timestamps before any model code.\nVenue: ${labels.venue}.\nModality: ${labels.modality}.\n${
          isKaggle
            ? "Confirm train/test schema parity and synthetic quirks."
            : "Also audit how the label was created (e.g. chargeback lag) so leakage does not hide in the definition."
        }`,
      },
      {
        title: "Stage 2 — Lock leak-free validation",
        priority: 20,
        plan: `Chosen split: ${labels.validation}.\nDo not change folds/random_state casually after this stage — it is the yardstick for every later claim.\n${
          isKaggle
            ? "Use stratified folds so each fold mirrors the target rate on static contest data."
            : "Prefer time-based train/valid/test plus group integrity (same customer/entity stays in one split)."
        }`,
      },
      {
        title: "Stage 3 — 60-second dumb baseline",
        priority: 30,
        plan: baselinePlan,
      },
      {
        title: "Stage 4 — Domain feature engineering",
        priority: 40,
        plan: `Create ratios, velocities, historical rates (OOF target encoding), and interactions. Keep a feature only if it beats Stage 3 on the locked validation split. ~80% of real gains usually live here — not in a bigger neural net.`,
      },
      {
        title: isKaggle
          ? "Stage 5 — Kaggle squeeze path (final 40%)"
          : "Stage 5 — Commercial deploy path (final 40%)",
        priority: 50,
        plan:
          (isKaggle
            ? `Primary goal: squeeze every 0.1 bps on a static test file.\nExpect diverse ensembles (LGBM/XGB/CatBoost/linear/MLP) and careful stacking only after Stages 1–4 are solid.\nUse LLMs/GPT even on numeric columns only when the dataset is known synthetic-from-NN — never as Step 1.`
            : `Primary goal: reliable ROI, fast inference, maintainability, explainability.\nPrefer 1–2 fast calibrated models (usually tuned LightGBM/CatBoost + Platt).\nUse LLMs only when a column is real human text (chat, receipts, emails). Next: API deploy, drift alerts, dollar thresholds.`) +
          `\n\nModality strategy ladder (${labels.modality}):\n${strategyLadderPlan(w)}`,
      },
    ];
    const selected = paradigmShiftCatalog(w).filter(
      (s) => (w.paradigmShifts || []).indexOf(s.id) >= 0
    );
    selected.forEach((s, i) => {
      items.push({
        title: "Paradigm shift — " + s.title,
        priority: 60 + i * 10,
        plan: `${s.detail}\n\nGate: only after Stages 1–3 are executed on locked CV. If it fails Stage-3 beat, mark dead-end and return to the default ladder.\nModality context: ${labels.modality}.`,
      });
    });
    return items;
  }

  function buildPlaybookNote(w) {
    const labels = playbookLabels(w);
    const shiftLines = labels.shifts.length
      ? labels.shifts.map((s) => `  - ${s.title}`).join("\n")
      : "  - (none selected)";
    const ladderLines = labels.strategies
      .map((s) => `  - [${s.tier}] ${s.title}`)
      .join("\n");
    return [
      "Playbook locked at project create:",
      `• Venue: ${labels.venue}`,
      `• Modality: ${labels.modality}`,
      `• Validation: ${labels.validation}`,
      `• Baseline: ${labels.baseline}`,
      `• Goal threshold: ${w.threshold}`,
      "• Strategy ladder:",
      ladderLines,
      "• Paradigm shifts (optional later):",
      shiftLines,
      "Order: EDA → CV lock → dumb baseline → domain features → path split → optional paradigm shifts. Do not start with a heavy DL/GPT model.",
    ].join("\n");
  }

  async function seedProjectPlaybook(projectId, w) {
    if (w.seedRoadmap === false) return;
    const strategies = buildPlaybookRoadmap(w);
    for (const s of strategies) {
      await api("/v1/projects/" + projectId + "/roadmap", {
        method: "POST",
        body: JSON.stringify({
          title: s.title,
          plan: s.plan,
          priority: s.priority,
          status: "planned",
        }),
      });
    }
    await api("/v1/projects/" + projectId + "/progress", {
      method: "POST",
      body: JSON.stringify({ note: buildPlaybookNote(w) }),
    });
  }

  function captureWizardFields() {
    const w = state.wizard || defaultWizard();
    const nameEl = document.getElementById("wiz-name");
    const thrEl = document.getElementById("wiz-threshold");
    const kaggleEl = document.getElementById("wiz-kaggle");
    const gitEl = document.getElementById("wiz-git");
    const seedEl = document.getElementById("wiz-seed-roadmap");
    if (nameEl) w.name = nameEl.value.trim();
    if (thrEl) w.threshold = thrEl.value.trim();
    if (kaggleEl) w.kaggle = kaggleEl.value.trim();
    if (gitEl) w.git = gitEl.value.trim();
    if (seedEl) w.seedRoadmap = !!seedEl.checked;
    const kind = document.querySelector('input[name="wiz-kind"]:checked');
    const modality = document.querySelector('input[name="wiz-modality"]:checked');
    const validation = document.querySelector('input[name="wiz-validation"]:checked');
    const baseline = document.querySelector('input[name="wiz-baseline"]:checked');
    if (kind) w.kind = kind.value;
    if (modality) w.modality = modality.value;
    if (validation) w.validation = validation.value;
    if (baseline) w.baseline = baseline.value;
    const shiftBoxes = document.querySelectorAll('input[name="wiz-shift"]:checked');
    if (shiftBoxes.length || document.querySelector('input[name="wiz-shift"]')) {
      w.paradigmShifts = Array.prototype.map.call(shiftBoxes, (el) => el.value);
    }
    state.wizard = w;
    return w;
  }

  function renderWizard() {
    showChrome("studio");
    if (!state.wizard) state.wizard = defaultWizard();
    const w = state.wizard;
    const steps = wizardSteps();
    const stepName = steps[w.step] || "venue";
    const meta = wizardStepMeta(stepName);
    const needsCatalog = stepName === "strategies" || stepName === "review" || stepName === "baseline";
    if (needsCatalog && !state.playbookCatalogLoading) {
      const key = (w.modality || "tabular") + "|" + (w.kind || "standalone");
      if (state.playbookCatalogKey !== key || !state.playbookCatalog) {
        state.playbookCatalogLoading = true;
        ensurePlaybookCatalog(w, true)
          .catch((e) => {
            state.error = "Playbook catalog: " + String(e.message || e);
          })
          .finally(() => {
            state.playbookCatalogLoading = false;
            renderWizard();
          });
      }
    }
    let panel = "";

    if (stepName === "venue") {
      panel = `
<label class="studio-label" for="wiz-name">Project name</label>
<input class="studio-input" id="wiz-name" value="${escText(w.name || "")}" placeholder="e.g. playground-cc or fraud-v3" autocomplete="off" />
<p class="studio-label mt-4">Venue</p>
<div class="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label="Venue">
  ${wizardChoice("wiz-kind", "standalone", w.kind, "Commercial / real-world", "ROI, latency, drift, explainability. Time + group CV later.")}
  ${wizardChoice("wiz-kind", "kaggle", w.kind, "Kaggle competition", "Static test file. Stratified CV. Final 40% is LB squeeze.")}
</div>`;
    } else if (stepName === "modality") {
      panel = `
<p class="mb-3 text-sm text-mist-400">This only sets the recommended baseline family. You still start with EDA and a locked CV.</p>
<div class="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label="Data modality">
  ${wizardChoice("wiz-modality", "tabular", w.modality, "Structured tabular", "Rows & columns → LightGBM / XGB / CatBoost + linear. 99% of commercial tabular stops here.")}
  ${wizardChoice("wiz-modality", "text", w.modality, "Text / documents", "Chat, tickets, code → DeBERTa / embeddings after a linear baseline.")}
  ${wizardChoice("wiz-modality", "vision", w.modality, "Images / video / audio", "Start with pretrained backbones + a light head, not a scratch CNN.")}
  ${wizardChoice("wiz-modality", "sequential", w.modality, "Sequential events", "Rolling-window tree features first; sequence nets only if volume justifies it.")}
</div>`;
    } else if (stepName === "validation") {
      panel = `
<p class="mb-3 text-sm text-mist-400">The single most important step. Suggested default follows your venue — change only with a reason.</p>
<div class="grid gap-2" role="radiogroup" aria-label="Validation strategy">
  ${wizardChoice("wiz-validation", "skf5", w.validation, "5-fold StratifiedKFold", "Best default for static / synthetic Kaggle tables with a rare target.")}
  ${wizardChoice("wiz-validation", "time_group", w.validation, "Time holdout + group split", "Best default for live commercial streams — no future peeking, entities stay intact.")}
  ${wizardChoice("wiz-validation", "group_kfold", w.validation, "GroupKFold", "When leakage is entity-level but time is weak (use mymlfw.cv.run_oof).")}
</div>`;
    } else if (stepName === "baseline") {
      const def = w.kind === "kaggle" ? "0.70" : "0.30";
      panel = `
<p class="mb-3 text-sm text-mist-400">No GPU. No GPT. Get a 60-second score to beat, then engineer features against the locked CV.</p>
<div class="grid gap-2 sm:grid-cols-2" role="radiogroup" aria-label="Baseline model">
  ${wizardChoice("wiz-baseline", "lightgbm", w.baseline, "LightGBM", "Default for tabular — fast CPU, strong importances.")}
  ${wizardChoice("wiz-baseline", "logistic", w.baseline, "Logistic / Ridge", "Strong dumb baseline; great first pass on sparse / text embeddings.")}
  ${wizardChoice("wiz-baseline", "xgboost", w.baseline, "XGBoost", "Use when LGBM parity checks or library constraints require it.")}
  ${wizardChoice("wiz-baseline", "catboost", w.baseline, "CatBoost", "Strong with high-cardinality categoricals.")}
</div>
<label class="studio-label mt-4" for="wiz-threshold">Primary goal threshold to beat</label>
<input class="studio-input" id="wiz-threshold" value="${escText(w.threshold || def)}" inputmode="decimal" />
<p class="mt-1 text-xs text-mist-500">Maps to ${
        w.kind === "kaggle" ? "kaggle_public / public_score" : "notebook_score / cv_mean"
      }.</p>`;
    } else if (stepName === "strategies") {
      const ladder = modalityStrategyCatalog(w.modality);
      const shifts = paradigmShiftCatalog(w);
      const selected = w.paradigmShifts || [];
      const tierTone = { default: "text-emerald-300", escalate: "text-amber-200", paradigm: "text-sky-300" };
      const loading =
        state.playbookCatalogLoading || (!ladder.length && !state.error)
          ? `<p class="mb-3 text-sm text-mist-400">Loading shared playbook catalog…</p>`
          : "";
      panel = `
${loading}
<p class="mb-3 text-sm text-mist-400">Strategy ladder for <span class="text-signal">${escText(
        playbookLabels(w).modality
      )}</span> (same source as <code class="inline-code">mymlfw playbook strategies</code>). Climb only after the locked CV baseline is beaten.</p>
<ul class="mb-5 space-y-2">
  ${
    ladder.length
      ? ladder
          .map(
            (s) => `<li class="rounded-xl border border-ink-700 bg-ink-950/50 px-3 py-2">
      <div class="flex flex-wrap items-center gap-2">
        <span class="font-mono text-[10px] uppercase tracking-[0.1em] ${tierTone[s.tier] || "text-mist-400"}">${escText(
          s.tier
        )}</span>
        <span class="text-sm font-medium text-signal">${escText(s.title)}</span>
      </div>
      <p class="mt-1 text-xs leading-relaxed text-mist-400">${escText(s.detail)}</p>
    </li>`
          )
          .join("")
      : `<li class="text-sm text-mist-500">No strategies loaded yet.</li>`
  }
</ul>
<p class="studio-label">Possible paradigm shifts (optional later)</p>
<p class="mb-2 text-xs text-mist-500">Tick shifts that might apply after Stages 1–3. Each seeds a gated Roadmap item — not a license to skip EDA.</p>
<div class="grid gap-2">
  ${
    shifts.length
      ? shifts
          .map((s) => {
            const on = selected.indexOf(s.id) >= 0;
            return `<label class="flex cursor-pointer gap-3 rounded-xl border p-3 ${
              on ? "border-sky-500/40 bg-sky-500/10" : "border-ink-700 bg-ink-950/40 hover:border-ink-500"
            }">
      <input type="checkbox" class="mt-1" name="wiz-shift" value="${escText(s.id)}" ${on ? "checked" : ""} />
      <span class="min-w-0">
        <span class="block text-sm font-medium text-signal">${escText(s.title)}</span>
        <span class="mt-0.5 block text-xs leading-relaxed text-mist-400">${escText(s.detail)}</span>
      </span>
    </label>`;
          })
          .join("")
      : `<p class="text-sm text-mist-500">No venue-specific shifts for this modality — stay on the default ladder.</p>`
  }
</div>`;
    } else if (stepName === "link") {
      panel =
        w.kind === "kaggle"
          ? `
<label class="studio-label" for="wiz-kaggle">Kaggle competition slug</label>
<input class="studio-input" id="wiz-kaggle" value="${escText(w.kaggle || "")}" placeholder="playground-series-s6e11" autocomplete="off" />
<label class="studio-label" for="wiz-git">Git remote (optional)</label>
<input class="studio-input" id="wiz-git" value="${escText(w.git || "")}" placeholder="https://github.com/org/repo.git" />`
          : `
<label class="studio-label" for="wiz-git">Git remote (optional)</label>
<input class="studio-input" id="wiz-git" value="${escText(w.git || "")}" placeholder="https://github.com/org/repo.git" />
<p class="mt-2 text-sm text-mist-400">You can link git later from Ops. No Kaggle slug for commercial projects.</p>`;
    } else {
      const labels = playbookLabels(w);
      const roadmap = buildPlaybookRoadmap(w);
      panel = `
<div class="rounded-xl border border-ink-700 bg-ink-950/50 p-4">
  <dl class="grid gap-2 text-sm sm:grid-cols-2">
    <div><dt class="text-mist-500">Name</dt><dd class="font-medium text-signal">${escText(w.name || "—")}</dd></div>
    <div><dt class="text-mist-500">Venue</dt><dd class="text-mist-200">${escText(labels.venue)}</dd></div>
    <div><dt class="text-mist-500">Modality</dt><dd class="text-mist-200">${escText(labels.modality)}</dd></div>
    <div><dt class="text-mist-500">Validation</dt><dd class="text-mist-200">${escText(labels.validation)}</dd></div>
    <div><dt class="text-mist-500">Baseline</dt><dd class="text-mist-200">${escText(labels.baseline)}</dd></div>
    <div><dt class="text-mist-500">Threshold</dt><dd class="tabular-nums text-mist-200">${escText(w.threshold)}</dd></div>
    <div><dt class="text-mist-500">Paradigm shifts</dt><dd class="text-mist-200">${escText(
      labels.shifts.length ? labels.shifts.map((s) => s.title).join("; ") : "none"
    )}</dd></div>
    <div><dt class="text-mist-500">Kaggle</dt><dd class="font-mono text-xs text-mist-300">${escText(w.kaggle || "—")}</dd></div>
    <div><dt class="text-mist-500">Git</dt><dd class="font-mono text-xs text-mist-300">${escText(w.git || "—")}</dd></div>
  </dl>
  <div class="mt-4 border-t border-ink-700 pt-3">
    <p class="text-[10px] uppercase tracking-[0.12em] text-mist-500">Modality ladder</p>
    <ul class="mt-2 space-y-1 text-xs text-mist-400">
      ${labels.strategies
        .map(
          (s) =>
            `<li><span class="text-mist-500">[${escText(s.tier)}]</span> ${escText(s.title)}</li>`
        )
        .join("")}
    </ul>
  </div>
</div>
<label class="mt-4 flex cursor-pointer items-start gap-3 rounded-xl border border-ink-700 bg-ink-950/40 p-3">
  <input type="checkbox" id="wiz-seed-roadmap" class="mt-1" ${w.seedRoadmap !== false ? "checked" : ""} />
  <span>
    <span class="block text-sm font-medium text-signal">Seed Stages 1–5${
      labels.shifts.length ? " + " + labels.shifts.length + " paradigm shift(s)" : ""
    } on Roadmap</span>
    <span class="mt-0.5 block text-xs text-mist-400">EDA → CV lock → dumb baseline → features → ${
      w.kind === "kaggle" ? "Kaggle squeeze" : "commercial deploy"
    } path${labels.shifts.length ? " → gated paradigm shifts" : ""}.</span>
  </span>
</label>
<ol class="mt-4 space-y-2 text-xs text-mist-400">
  ${roadmap
    .map(
      (s, i) =>
        `<li class="rounded-lg border border-ink-800 px-3 py-2"><span class="text-mist-500">${i + 1}.</span> ${escText(s.title)}</li>`
    )
    .join("")}
</ol>`;
    }

    const isLast = w.step >= steps.length - 1;
    const stepPct = ((w.step + 1) / steps.length) * 100;
    const stepper = steps
      .map((id, i) => {
        const m = wizardStepMeta(id);
        const done = i < w.step;
        const current = i === w.step;
        const cls = current
          ? "border-signal/40 bg-signal/10 text-signal"
          : done
            ? "border-ink-600 bg-ink-800 text-mist-200"
            : "border-ink-800 bg-transparent text-mist-500";
        return `<li class="rounded-md border px-2 py-1 text-[11px] uppercase tracking-[0.08em] ${cls}">${escText(m.label)}</li>`;
      })
      .join("");
    const labels = playbookLabels(w);
    const body = `
<section class="mx-auto grid max-w-5xl gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
  <div>
    <div class="mb-5">
      <p class="text-xs uppercase tracking-[0.14em] text-mist-500">New project · playbook wizard</p>
      <h1 class="mt-1 text-3xl font-semibold tracking-tight text-signal">${escText(meta.title)}</h1>
      <p class="mt-1 text-sm text-mist-400">Step ${w.step + 1} of ${steps.length} · never start with a heavy model</p>
      <div class="mt-4 h-1.5 overflow-hidden rounded-full bg-ink-800" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(stepPct)}">
        <div class="h-full bg-signal transition-[width] duration-300" style="width:${stepPct}%"></div>
      </div>
      <ol class="mt-3 flex flex-wrap gap-1.5">${stepper}</ol>
    </div>
    <form id="wizard-form" class="studio-card space-y-1">${panel}
      <div class="flex flex-wrap items-center gap-2 pt-5">
        <button type="button" class="studio-ghost" id="wiz-cancel">Cancel</button>
        ${w.step > 0 ? `<button type="button" class="studio-ghost" id="wiz-back">Back</button>` : ""}
        <button type="submit" class="studio-cta ml-auto" id="wiz-next">${isLast ? "Create project" : "Continue"}</button>
      </div>
    </form>
  </div>
  <aside class="studio-card h-fit lg:sticky lg:top-4">
    <h2 class="mb-2 text-sm font-medium text-signal">Expert coach</h2>
    <p class="text-sm leading-relaxed text-mist-300">${escText(wizardCoach(w, stepName))}</p>
    <div class="mt-4 border-t border-ink-700 pt-3 text-xs text-mist-500 space-y-1.5">
      <div><span class="text-mist-400">Venue</span> · ${escText(labels.venue)}</div>
      <div><span class="text-mist-400">Data</span> · ${escText(labels.modality)}</div>
      <div><span class="text-mist-400">CV</span> · ${escText(labels.validation)}</div>
      <div><span class="text-mist-400">Baseline</span> · ${escText(labels.baseline)}</div>
      <div><span class="text-mist-400">Shifts</span> · ${escText(
        String((w.paradigmShifts || []).length)
      )} selected</div>
    </div>
  </aside>
</section>`;
    app.innerHTML = shell("Studio / new", body, "");
    bindShell(() => {
      function pruneParadigmShifts() {
        const allowed = new Set(paradigmShiftCatalog(state.wizard).map((s) => s.id));
        state.wizard.paradigmShifts = (state.wizard.paradigmShifts || []).filter((id) =>
          allowed.has(id)
        );
      }
      document.getElementById("wiz-cancel").onclick = () => {
        state.error = "";
        state.wizard = null;
        setRoute("studio");
      };
      const back = document.getElementById("wiz-back");
      if (back) {
        back.onclick = () => {
          captureWizardFields();
          state.wizard.step = Math.max(0, (state.wizard.step || 0) - 1);
          state.error = "";
          renderWizard();
        };
      }
      document.querySelectorAll('input[name="wiz-kind"]').forEach((el) => {
        el.onchange = () => {
          captureWizardFields();
          applyVenueDefaults(state.wizard);
          state.playbookCatalogKey = "";
          pruneParadigmShifts();
          renderWizard();
        };
      });
      document.querySelectorAll('input[name="wiz-modality"]').forEach((el) => {
        el.onchange = () => {
          captureWizardFields();
          if (state.wizard.modality === "text") state.wizard.baseline = "logistic";
          if (state.wizard.modality === "tabular") state.wizard.baseline = "lightgbm";
          if (state.wizard.modality === "vision" || state.wizard.modality === "sequential") {
            state.wizard.baseline = "lightgbm";
          }
          state.playbookCatalogKey = "";
          pruneParadigmShifts();
          renderWizard();
        };
      });
      document.getElementById("wizard-form").onsubmit = async (ev) => {
        ev.preventDefault();
        const nextBtn = document.getElementById("wiz-next");
        const cur = captureWizardFields();
        const stepsNow = wizardSteps();
        const name = stepsNow[cur.step] || "venue";

        if (name === "venue" && !cur.name) {
          state.error = "Enter a project name";
          renderWizard();
          return;
        }
        if (name === "baseline") {
          const threshold = Number(cur.threshold);
          if (!Number.isFinite(threshold)) {
            state.error = "Threshold must be a number";
            renderWizard();
            return;
          }
        }
        if (cur.step < stepsNow.length - 1) {
          cur.step += 1;
          if (name === "venue") applyVenueDefaults(cur);
          state.wizard = cur;
          state.error = "";
          renderWizard();
          return;
        }

        const threshold = Number(cur.threshold);
        if (!Number.isFinite(threshold)) {
          state.error = "Threshold must be a number";
          cur.step = stepsNow.indexOf("baseline");
          state.wizard = cur;
          renderWizard();
          return;
        }
        const kind = cur.kind === "kaggle" ? "kaggle" : "standalone";
        if (kind === "kaggle" && !String(cur.kaggle || "").trim()) {
          state.error = "Kaggle competition slug is required";
          cur.step = stepsNow.indexOf("link");
          state.wizard = cur;
          renderWizard();
          return;
        }
        const goal =
          kind === "kaggle"
            ? {
                title: "Kaggle public >= " + threshold,
                kind: "kaggle_public",
                metric_key: "public_score",
                threshold,
                direction: "maximize",
              }
            : {
                title: "Notebook CV >= " + threshold,
                kind: "notebook_score",
                metric_key: "cv_mean",
                threshold,
                direction: "maximize",
              };
        try {
          if (nextBtn) {
            nextBtn.disabled = true;
            nextBtn.textContent = "Creating…";
          }
          const created = await api("/v1/projects", {
            method: "POST",
            body: JSON.stringify({
              name: cur.name,
              kind,
              goals: [goal],
              kaggle_competition: cur.kaggle || "",
              git_remote: cur.git || "",
            }),
          });
          try {
            await seedProjectPlaybook(created.id, cur);
          } catch (seedErr) {
            state.notice =
              "Created " +
              created.slug +
              " (playbook seed partial: " +
              String(seedErr.message || seedErr) +
              ")";
          }
          await loadStudio();
          if (!state.notice) state.notice = "Created " + created.slug + " · Stages 1–5 seeded";
          state.error = "";
          state.wizard = null;
          state.mode = "ROADMAP";
          state.roadmapFilter = "planned";
          setRoute("studio/" + created.id + "/roadmap");
        } catch (e) {
          state.error = String(e.message || e);
          renderWizard();
        }
      };
    });
  }

  function mcpCursorSnippet(pat) {
    const token = pat || "<PASTE_PAT_HERE>";
    return `{
  "mcpServers": {
    "mymlfw": {
      "url": "http://127.0.0.1:8100/mcp",
      "headers": {
        "Authorization": "Bearer ${token}"
      }
    }
  }
}`;
  }

  function mcpAgentFollowUp() {
    return [
      "Stop narrating-only. From now on keep the mymlfw Studio project updated via MCP before each user-visible reply.",
      "",
      "1. Load MCP prompt campaign_sync (or follow docs/how-to/agent-mcp-campaign-sync.md).",
      "2. Orient: list_projects → get_project_dashboard — bind to the existing Studio project (do not create Demo Campaign).",
      "3. After every real step (download, notebook reuse, CV number, submit, dead end): call the matching MCP tools (register_external_asset, propose_lever_execution, report_mission_progress, complete_mission, …) with a fresh idempotency_key.",
      "4. If a tool is missing, wrong, or you cannot sync an action: call report_mcp_gap(title, needed_capability, context, workaround, severity, suggested_tool_name, idempotency_key) AND tell me in chat what is missing.",
      "5. Do not claim Studio is updated unless MCP (or Studio HTTP) wrote the state.",
    ].join("\n");
  }

  function renderSettings() {
    showChrome("studio");
    const s = state.settings || state.me || {};
    const user = s.user || {};
    const org = s.org || {};
    const ent = org.entitlements || {};
    const flags = org.feature_flags || {};
    const pats = Array.isArray(state.pats) ? state.pats : [];
    const activePats = pats.filter((p) => !p.revoked_at);
    const minted = state.mintedPat || "";
    const hasActivePat = activePats.length > 0;
    const patRows = pats
      .map(
        (p) =>
          `<tr><td class="font-mono text-xs">${escText(p.token_prefix || "")}</td><td>${escText((p.scopes || []).join(", "))}</td><td>${p.revoked_at ? "revoked" : "active"}</td><td>${p.revoked_at ? "" : `<button type="button" class="studio-link pat-revoke" data-id="${escText(p.token_id || "")}">[ revoke ]</button>`}</td></tr>`
      )
      .join("");
    const body = `
<section>
  <div class="mb-6">
    <h1 class="text-3xl font-semibold tracking-tight text-signal">Settings</h1>
    <p class="mt-2 text-sm text-mist-400">Account, workspace, and agent MCP connect.</p>
    ${state.notice ? `<p class="mt-2 text-sm text-signal-warn">${escText(state.notice)}</p>` : ""}
    ${state.error ? `<p class="mt-2 text-sm text-signal-warn">${escText(state.error)}</p>` : ""}
  </div>

  <section class="studio-card mb-6 border border-signal/30">
    <h2 class="mb-2 text-lg font-medium text-signal">Agent connect (MCP)</h2>
    <p class="mb-3 text-sm text-mist-400">1) Mint a PAT · 2) Add it to Cursor MCP config · 3) Tell the agent to use prompt <code class="text-signal">campaign_sync</code> and follow <code class="text-signal">docs/how-to/agent-mcp-campaign-sync.md</code>.</p>
    <p class="mb-3 text-xs text-mist-500">Endpoint: <code class="text-signal">http://127.0.0.1:8100/mcp</code> · scope <code class="text-signal">mcp:worker</code> · <code class="text-mist-400">mcp_oauth</code> stays off (Bearer PAT, not OAuth).</p>
    <p class="mb-3 text-xs text-mist-500">One active PAT per workspace. Replacing invalidates the old token in Cursor.</p>
    <button type="button" class="studio-cta" id="mint-pat">${hasActivePat ? "Replace mcp:worker PAT" : "Mint mcp:worker PAT"}</button>
    ${
      minted
        ? `<div class="mt-4 space-y-2">
      <p class="text-sm text-signal-warn">Copy the PAT now — it is shown only once.</p>
      <pre class="overflow-x-auto rounded-lg border border-ink-600 bg-ink-950 p-3 font-mono text-xs text-signal">${escText(minted)}</pre>
      <p class="text-sm text-mist-400">Cursor MCP config (paste into mcp.json):</p>
      <pre class="overflow-x-auto rounded-lg border border-ink-600 bg-ink-950 p-3 font-mono text-xs text-mist-200">${escText(mcpCursorSnippet(minted))}</pre>
      <p class="text-sm text-mist-400">Paste this into a running agent chat (follow-up):</p>
      <pre class="overflow-x-auto rounded-lg border border-ink-600 bg-ink-950 p-3 text-xs text-mist-200">${escText(mcpAgentFollowUp())}</pre>
    </div>`
        : `<div class="mt-4 space-y-2">
      <p class="text-sm text-mist-500">Mint a PAT above, then copy Cursor config + the follow-up text.</p>
      <p class="text-sm text-mist-400">Follow-up to paste into a running agent (MCP must already be configured):</p>
      <pre class="overflow-x-auto rounded-lg border border-ink-600 bg-ink-950 p-3 text-xs text-mist-200">${escText(mcpAgentFollowUp())}</pre>
    </div>`
    }
    ${
      patRows
        ? `<table class="mt-4 w-full text-left text-sm"><thead><tr><th>Prefix</th><th>Scopes</th><th>Status</th><th></th></tr></thead><tbody>${patRows}</tbody></table>`
        : `<p class="mt-3 text-sm text-mist-500">No PATs minted yet for this org.</p>`
    }
  </section>

  <div class="mb-6 grid gap-3 sm:grid-cols-2">
    <section class="studio-card"><h2 class="mb-2 text-sm font-medium text-signal">Profile</h2><p>${escText(user.display_name || "")}</p><p class="text-sm text-mist-500">${escText(user.email || "")}</p></section>
    <section class="studio-card"><h2 class="mb-2 text-sm font-medium text-signal">Organization</h2><p>${escText(org.name || org.slug || "")}</p><p class="text-sm text-mist-500">plan ${escText(org.plan || "dev")}</p></section>
    <section class="studio-card"><h2 class="mb-2 text-sm font-medium text-signal">Entitlements</h2><p class="text-sm text-mist-500">projects ${escText(String(ent.max_private_projects ?? "—"))} · agents ${escText(String(ent.max_agents ?? "—"))} · advise/day ${escText(String(ent.advise_per_day ?? "—"))}</p></section>
    <section class="studio-card"><h2 class="mb-2 text-sm font-medium text-signal">Feature flags</h2><p class="text-sm text-mist-500">${Object.keys(flags).map((k) => k + "=" + (flags[k] ? "on" : "off")).join(" · ") || "none"}</p></section>
  </div>
  <button type="button" class="studio-ghost" id="back-studio">Back to studio</button>
</section>`;
    app.innerHTML = shell("Settings", body, "");
    bindShell(() => {
      document.getElementById("back-studio").onclick = () => setRoute("studio");
      const mint = document.getElementById("mint-pat");
      if (mint) {
        mint.onclick = async () => {
          const active = (Array.isArray(state.pats) ? state.pats : []).filter(
            (p) => !p.revoked_at
          );
          let replace = false;
          if (active.length) {
            const prefixes = active.map((p) => p.token_prefix || p.token_id || "?").join(", ");
            const ok = window.confirm(
              "An active MCP PAT already exists (" +
                prefixes +
                ").\n\nReplace it? The old token will stop working in Cursor until you paste the new one."
            );
            if (!ok) return;
            replace = true;
          }
          try {
            const created = await api("/v1/orgs/current/pats", {
              method: "POST",
              headers: { "Idempotency-Key": crypto.randomUUID() },
              body: JSON.stringify({
                scopes: ["mcp:worker"],
                label: "studio-mcp",
                replace,
              }),
            });
            state.mintedPat = created.token || "";
            state.pats = await api("/v1/orgs/current/pats");
            state.notice = replace
              ? "PAT replaced — copy the new token now; update Cursor mcp.json."
              : "PAT minted — copy it now; it will not be shown again.";
            state.error = "";
            renderSettings();
          } catch (err) {
            state.notice = "";
            state.error = String(err.message || err);
            renderSettings();
          }
        };
      }
      document.querySelectorAll(".pat-revoke").forEach((btn) => {
        btn.onclick = async () => {
          const id = btn.getAttribute("data-id");
          if (!id) return;
          try {
            await api("/v1/orgs/current/pats/" + encodeURIComponent(id), {
              method: "DELETE",
              headers: { "Idempotency-Key": crypto.randomUUID() },
            });
            if (state.mintedPat) state.mintedPat = "";
            state.pats = await api("/v1/orgs/current/pats");
            state.notice = "PAT revoked";
            renderSettings();
          } catch (err) {
            state.error = String(err.message || err);
            renderSettings();
          }
        };
      });
    });
  }

  function modePath(mode) {
    if (mode === "DEAD_ENDS") return "dead-ends";
    if (mode === "SOURCES") return "sources";
    if (mode === "ROADMAP") return "roadmap";
    if (mode === "GIT") return "git";
    return String(mode || "").toLowerCase();
  }

  function modeFromPath(seg) {
    const raw = String(seg || "brain").toLowerCase();
    if (raw === "dead-ends" || raw === "dead_ends" || raw === "deadends") return "DEAD_ENDS";
    if (raw === "sources" || raw === "source") return "SOURCES";
    if (raw === "roadmap") return "ROADMAP";
    if (raw === "git") return "GIT";
    return raw.toUpperCase();
  }

  const STUDIO_MODES = ["BRAIN", "GOALS", "DEAD_ENDS", "SOURCES", "ROADMAP", "GIT", "LAB", "KAGGLE", "OPS", "TRUST"];

  function modeNav(project) {
    const modes = [
      ["BRAIN", "Overview"],
      ["GOALS", "Goals"],
      ["DEAD_ENDS", "Dead ends"],
      ["SOURCES", "Sources"],
      ["ROADMAP", "Roadmap"],
      ["GIT", "Git"],
      ["LAB", "Lab"],
      ["KAGGLE", "Kaggle"],
      ["OPS", "Ops"],
      ["TRUST", "Trust"],
    ].filter((pair) => pair[0] !== "KAGGLE" || (project && project.kind === "kaggle"));
    return `<nav class="mb-6 flex flex-wrap gap-1 border-b border-ink-700 pb-3">${modes
      .map(
        ([id, label]) =>
          `<button type="button" class="studio-tab ${state.mode === id ? "studio-tab-on" : ""}" data-mode="${id}">${label}</button>`
      )
      .join("")}</nav>`;
  }

  function stat(label, value, hint) {
    return `<article class="studio-stat"><span>${escText(label)}</span><strong>${escText(value)}</strong>${hint ? `<em>${escText(hint)}</em>` : ""}</article>`;
  }

  function panelCard(title, bodyHtml) {
    return `<section class="studio-card"><h2 class="mb-2 text-sm font-medium text-signal">${escText(title)}</h2>${bodyHtml}</section>`;
  }

  function overviewValidationHtml() {
    const roadmap = state.roadmapList || [];
    const executed = roadmap
      .filter((s) => s.status === "executed")
      .slice()
      .sort((a, b) => (a.priority || 100) - (b.priority || 100));
    const active = roadmap.filter((s) => s.status === "in_progress");
    const stage2 = executed.find((s) => /stage\s*2/i.test(s.title || ""));
    const lockedCv = stage2 && stage2.result_metric != null ? stage2.result_metric : null;
    const rows = executed
      .map((s) => {
        const metric =
          s.result_metric != null
            ? `<span class="font-semibold tabular-nums text-signal">${fmtNum(s.result_metric)}</span>`
            : `<span class="text-mist-500">—</span>`;
        const result = String(s.result || "").trim();
        const short =
          result.length > 160 ? result.slice(0, 157) + "…" : result || "Recorded";
        return `<li class="rounded-lg border border-ink-700 bg-ink-950/60 px-3 py-2">
          <div class="flex flex-wrap items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <div class="text-sm font-medium text-signal">${escText(s.title || "")}</div>
              <p class="mt-1 text-xs leading-relaxed text-mist-400">${escText(short)}</p>
            </div>
            <div class="text-right">${metric}<div class="text-[10px] uppercase tracking-[0.1em] text-mist-500">executed</div></div>
          </div>
        </li>`;
      })
      .join("");
    const next = active
      .map(
        (s) =>
          `<div class="text-sm text-amber-200">${escText(s.title || "")} <span class="text-mist-500">in progress</span></div>`
      )
      .join("");
    const recentMissions = (state.missionsList || [])
      .filter((m) => m.status === "succeeded")
      .slice(0, 4)
      .map(
        (m) =>
          `<li class="text-xs text-mist-400"><span class="text-mist-500">${escText(m.mission_type || "mission")}</span> · ${escText(m.title || m.id || "")}</li>`
      )
      .join("");
    if (!executed.length && !active.length) {
      return `<section class="studio-card"><h2 class="mb-2 text-sm font-medium text-signal">Validation roadmap</h2><p class="text-sm text-mist-500">No roadmap results yet. Sync stages via MCP or open Roadmap.</p></section>`;
    }
    return `<section class="studio-card">
      <div class="mb-3 flex flex-wrap items-end justify-between gap-2">
        <h2 class="text-sm font-medium text-signal">Validation roadmap</h2>
        ${
          lockedCv != null
            ? `<div class="text-right"><div class="text-[10px] uppercase tracking-[0.1em] text-mist-500">Locked CV (Stage 2)</div><div class="text-xl font-semibold tabular-nums text-signal">${fmtNum(lockedCv)}</div></div>`
            : ""
        }
      </div>
      ${next ? `<div class="mb-3 space-y-1">${next}</div>` : ""}
      <ul class="space-y-2">${rows || `<li class="text-sm text-mist-500">No executed stages yet.</li>`}</ul>
      ${
        recentMissions
          ? `<div class="mt-4 border-t border-ink-700 pt-3"><div class="mb-1 text-[10px] uppercase tracking-[0.1em] text-mist-500">Recent missions</div><ul class="space-y-1">${recentMissions}</ul></div>`
          : ""
      }
      <p class="mt-3"><button type="button" class="studio-link" id="goto-roadmap">[ open Roadmap ]</button></p>
    </section>`;
  }

  function overviewBody(project, dash) {
    const h = (dash && dash.header) || {};
    const scores = (dash && dash.scores) || {};
    const levers = (dash && dash.levers) || {};
    const missions = (dash && dash.missions) || {};
    const dead = (dash && dash.dead_ends) || {};
    const kaggle = (dash && dash.kaggle) || {};
    const openLever = (state.leversList || []).find((L) => L.status === "open");
    const publicScore =
      scores.best_public != null ? scores.best_public : kaggle.public_score;
    const stage2 = (state.roadmapList || []).find(
      (s) => s.status === "executed" && /stage\s*2/i.test(s.title || "")
    );
    const lockedCv = stage2 && stage2.result_metric != null ? stage2.result_metric : null;
    const train = state.trainStrip
      ? `<p class="mt-2 text-xs text-signal-warn">training · fold ${escText(String(state.trainStrip.fold || "—"))}</p>`
      : "";
    const status = String(h.primary_status || "OPEN").toUpperCase();
    const chart = chartsBarRows([
      { label: "Progress", size: h.progress_pct, display: fmtPct(h.progress_pct) },
      { label: "Goals", size: h.goals_met_ratio, display: fmtPct(h.goals_met_ratio) },
      { label: "Levers", size: h.lever_close_rate, display: fmtPct(h.lever_close_rate) },
      { label: "Missions", size: h.mission_success_rate, display: fmtPct(h.mission_success_rate) },
    ]);
    return `
${modeNav(project)}
<section>
  <div class="mb-6 flex flex-wrap items-start justify-between gap-4">
    <div>
      <h1 class="text-3xl font-semibold tracking-tight text-signal">${escText((project && (project.name || project.slug)) || "Project")}</h1>
      <p class="mt-2 flex flex-wrap items-center gap-2 text-sm text-mist-400">
        <span class="rounded-full border border-ink-600 px-2 py-0.5 text-xs tracking-wide text-signal">${escText(status)}</span>
        <span>${escText(h.primary_goal_title || "No primary goal")}</span>
        <span class="text-mist-500">thr ${fmtNum(h.primary_threshold)} · now ${fmtNum(h.primary_latest)} · gap ${fmtNum(h.primary_gap)}</span>
      </p>
      ${train}
    </div>
    <button type="button" class="studio-cta" id="assign">Assign next mission</button>
  </div>
  <div class="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
    ${stat("Progress", fmtPct(h.progress_pct), "0.5 goals · 0.3 levers · 0.2 missions")}
    ${stat("Public", fmtNum(publicScore), kaggle.rank != null ? "rank " + kaggle.rank : project && project.kind === "kaggle" ? "LB synced" : "n/a")}
    ${stat("Best CV", fmtNum(scores.best_cv), lockedCv != null ? "locked baseline " + fmtNum(lockedCv) : "gap to thr " + fmtNum(h.primary_gap))}
    ${stat("Open work", String(levers.open || 0), (missions.queued || 0) + " queued · " + (missions.running || 0) + " running · " + (dead.count || 0) + " dead ends")}
  </div>
  <div class="mb-6">${overviewValidationHtml()}</div>
  <div class="mb-6 grid gap-4 lg:grid-cols-2">
    <section class="studio-card">
      <h2 class="mb-4 text-sm font-medium text-signal">Campaign mix</h2>
      ${chart}
    </section>
    <section class="studio-card">
      <h2 class="mb-3 text-sm font-medium text-signal">Status</h2>
      <dl class="space-y-2 text-sm">
        <div class="flex justify-between gap-4"><dt class="text-mist-500">Kind</dt><dd class="text-signal">${escText((project && project.kind) || "—")}</dd></div>
        <div class="flex justify-between gap-4"><dt class="text-mist-500">Public / rank</dt><dd class="text-signal">${fmtNum(publicScore)}${kaggle.rank != null ? " · #" + escText(String(kaggle.rank)) : ""}</dd></div>
        <div class="flex justify-between gap-4"><dt class="text-mist-500">ADV AUC</dt><dd class="text-signal">${fmtNum(h.adv_auc)} · ${escText(h.adv_auc_label || "UNKNOWN")}</dd></div>
        <div class="flex justify-between gap-4"><dt class="text-mist-500">Levers</dt><dd class="text-signal">${levers.open || 0} open / ${levers.closed || 0} closed · ${levers.kills || 0} kills</dd></div>
        <div class="flex justify-between gap-4"><dt class="text-mist-500">Missions</dt><dd class="text-signal">${missions.queued || 0}q · ${missions.running || 0}run · ${missions.succeeded || 0}ok · ${escText(missions.last_mission_type || "—")}</dd></div>
      </dl>
    </section>
  </div>
  <p class="mb-6 flex flex-wrap gap-4">
    <button type="button" class="studio-link" id="open-lever">[ open lever ]</button>
    <button type="button" class="studio-link" id="record-progress">[ record progress ]</button>
    ${project && project.kind === "kaggle" ? `<button type="button" class="studio-link" id="goto-kaggle">[ open Kaggle ]</button>` : ""}
    ${openLever ? `<button type="button" class="studio-link" id="close-lever" data-id="${escText(openLever.id)}">[ close open lever ]</button>` : ""}
  </p>
  ${adviseHtmlSafe(state.advise)}
  <dialog id="progress-dialog" class="rounded-xl border border-ink-600 bg-ink-900 p-4 text-mist-200 shadow-card backdrop:bg-zinc-900/25">
    <form method="dialog" class="space-y-2">
      <h2 class="text-lg font-medium text-signal">Record progress</h2>
      <textarea class="studio-input" id="progress-note" rows="4" placeholder="Daily note"></textarea>
      <div class="flex gap-2 pt-2">
        <button type="submit" class="studio-cta" id="progress-save" value="save">Save</button>
        <button type="submit" class="studio-ghost" value="cancel">Cancel</button>
      </div>
    </form>
  </dialog>
  <dialog id="lever-dialog" class="rounded-xl border border-ink-600 bg-ink-900 p-4 text-mist-200 shadow-card backdrop:bg-zinc-900/25">
    <form method="dialog" class="space-y-1">
      <h2 class="mb-2 text-lg font-medium text-signal">Open lever</h2>
      <label class="studio-label" for="lever-var">Variable</label>
      <input class="studio-input" id="lever-var" value="probe" />
      <label class="studio-label" for="lever-goal">Goal id</label>
      <input class="studio-input" id="lever-goal" value="${escText(h.primary_goal_id || "")}" />
      <label class="studio-label" for="lever-low">Band low</label>
      <input class="studio-input" id="lever-low" value="0" />
      <label class="studio-label" for="lever-high">Band high</label>
      <input class="studio-input" id="lever-high" value="0.05" />
      <div class="flex gap-2 pt-3">
        <button type="submit" class="studio-cta" id="lever-save" value="save">Open</button>
        <button type="submit" class="studio-ghost" value="cancel">Cancel</button>
      </div>
    </form>
  </dialog>
</section>`;
  }

  function adviseHtmlSafe(advise) {
    if (!advise) return "";
    const items = (advise.proposed_missions || [])
      .map((m) => {
        const reason = String(m.rationale_md || "").split("Context:")[0].trim();
        const short = reason.length > 180 ? reason.slice(0, 177) + "…" : reason;
        return `<li><strong class="text-signal">${escText(m.title)}</strong>${short ? `<div class="text-xs text-mist-500">${escText(short)}</div>` : ""}</li>`;
      })
      .join("");
    return `<section class="studio-card"><h2 class="mb-2 text-sm font-medium text-signal">Next missions</h2><p class="mb-2 text-xs text-mist-500">Grounding ${fmtNum(advise.grounding_score, 2)}</p><ul class="space-y-2 text-sm">${items || "<li class=\"text-mist-500\">No mission passed the citation check.</li>"}</ul></section>`;
  }

  function goalsBody(project, dash) {
    const h = (dash && dash.header) || {};
    const folds = (project && project.folds) || {};
    const list = state.goalsList || [];
    const rows = list
      .map(
        (g) => `<tr data-goal="${escText(g.id)}">
      <td>${escText(g.title)}</td>
      <td>${escText(g.kind)}</td>
      <td>${fmtNum(g.threshold)}</td>
      <td>${fmtNum(g.best_value)}</td>
      <td><span class="pill">${escText(g.status)}</span></td>
      <td class="actions">
        <button type="button" class="linkish goal-met" data-id="${escText(g.id)}">[ met ]</button>
        <button type="button" class="linkish goal-abandon" data-id="${escText(g.id)}">[ abandon ]</button>
      </td>
    </tr>`
      )
      .join("");
    return `
${modeNav(project)}
<section class="page">
  <div class="page-head">
    <div>
      <h1>Goals</h1>
      <p class="lede">CRUD against /v1/projects/{id}/goals · folds / ADV_AUC from dashboard.</p>
    </div>
  </div>
  <div class="stats">
    ${stat("Active", String(list.filter((g) => g.status === "active").length))}
    ${stat("Met", String(list.filter((g) => g.status === "met").length))}
    ${stat("ADV AUC", fmtNum(h.adv_auc || folds.adv_auc), h.adv_auc_label || "UNKNOWN")}
    ${stat("Folds", String(folds.n_folds ?? "—"), (folds.folds_sha256 || h.folds_sha256 || "—").slice(0, 12))}
  </div>
  <section class="card span2">
    <h2>Goals</h2>
    ${rows ? `<table><thead><tr><th>Title</th><th>Kind</th><th>Thr</th><th>Best</th><th>Status</th><th></th></tr></thead><tbody>${rows}</tbody></table>` : `<p class="sub">No goals.</p>`}
  </section>
  <section class="card">
    <h2>Add goal</h2>
    <label for="goal-title">Title</label>
    <input id="goal-title" placeholder="CV floor" />
    <label for="goal-kind">Kind</label>
    <select id="goal-kind">
      <option value="notebook_score">notebook_score</option>
      <option value="kaggle_public">kaggle_public</option>
      <option value="kaggle_private">kaggle_private</option>
      <option value="cv_delta">cv_delta</option>
      <option value="custom">custom</option>
    </select>
    <label for="goal-metric">Metric key</label>
    <input id="goal-metric" value="cv_mean" />
    <label for="goal-thr">Threshold</label>
    <input id="goal-thr" value="0.30" />
    <button type="button" class="cta" id="goal-create">Create goal</button>
  </section>
</section>`;
  }

  function gitBody(project) {
    const info = state.gitInfo || {};
    const git = info.git || null;
    const linked = !!info.linked && git && git.remote;
    if (!linked) {
      return `
${modeNav(project)}
<section class="page">
  <div class="page-head">
    <div>
      <h1>Git</h1>
      <p class="lede">Link a repository to this project — details and public stats appear after you add it.</p>
    </div>
  </div>
  <section class="card">
    <h2>Add repository</h2>
    <label for="git-remote">Remote URL</label>
    <input id="git-remote" placeholder="https://github.com/org/repo.git or git@github.com:org/repo.git" />
    <button type="button" class="cta" id="git-link">Link repository</button>
    <p class="sub">GitHub remotes refresh public stats (stars, forks, language). Other hosts store the link only.</p>
  </section>
</section>`;
    }
    const topics = (git.topics || []).slice(0, 8).map((t) => `<span class="pill">${escText(t)}</span>`).join(" ");
    return `
${modeNav(project)}
<section class="page">
  <div class="page-head">
    <div>
      <h1>Git</h1>
      <p class="lede">${escText(git.full_name || git.remote || "Linked repository")}</p>
    </div>
    <div class="sec-actions">
      <button type="button" class="ghost" id="git-refresh">Refresh stats</button>
      <button type="button" class="linkish" id="git-unlink">[ unlink ]</button>
    </div>
  </div>
  <div class="stats">
    ${stat("Stars", git.stars != null ? String(git.stars) : "—")}
    ${stat("Forks", git.forks != null ? String(git.forks) : "—")}
    ${stat("Open issues", git.open_issues != null ? String(git.open_issues) : "—")}
    ${stat("Watchers", git.watchers != null ? String(git.watchers) : "—")}
  </div>
  <div class="grid">
    <section class="card span2">
      <h2>Repository</h2>
      <dl class="space-y-2 text-sm">
        <div class="flex justify-between gap-4"><dt class="text-mist-500">Remote</dt><dd class="font-mono text-xs break-all">${escText(git.remote || "")}</dd></div>
        <div class="flex justify-between gap-4"><dt class="text-mist-500">Host</dt><dd>${escText(git.host || "—")} · ${escText(git.provider || "")}</dd></div>
        <div class="flex justify-between gap-4"><dt class="text-mist-500">Default branch</dt><dd>${escText(git.default_branch || "—")}</dd></div>
        <div class="flex justify-between gap-4"><dt class="text-mist-500">Language</dt><dd>${escText(git.language || "—")}</dd></div>
        <div class="flex justify-between gap-4"><dt class="text-mist-500">License</dt><dd>${escText(git.license_spdx || "—")}</dd></div>
        <div class="flex justify-between gap-4"><dt class="text-mist-500">Size</dt><dd>${git.size_kb != null ? escText(String(git.size_kb)) + " KB" : "—"}</dd></div>
        <div class="flex justify-between gap-4"><dt class="text-mist-500">Last push</dt><dd>${escText(String(git.pushed_at || "—"))}</dd></div>
        <div class="flex justify-between gap-4"><dt class="text-mist-500">Visibility</dt><dd>${git.private == null ? "—" : git.private ? "private" : "public"}${git.archived ? " · archived" : ""}</dd></div>
      </dl>
      ${git.description ? `<p class="mt-3 text-sm text-mist-400">${escText(git.description)}</p>` : ""}
      ${topics ? `<p class="mt-2 flex flex-wrap gap-1">${topics}</p>` : ""}
      ${git.html_url ? `<p class="mt-3"><a class="studio-link" href="${escText(git.html_url)}" target="_blank" rel="noopener noreferrer">Open on host</a></p>` : ""}
      ${git.refresh_error ? `<p class="sub mt-2">Stats: ${escText(git.refresh_error)}</p>` : ""}
      ${git.refreshed_at ? `<p class="sub">Refreshed ${escText(String(git.refreshed_at))}</p>` : ""}
    </section>
    <section class="card">
      <h2>Replace remote</h2>
      <label for="git-remote">Remote URL</label>
      <input id="git-remote" value="${escText(git.remote || "")}" />
      <button type="button" class="cta" id="git-link">Save remote</button>
    </section>
  </div>
</section>`;
  }

  function roadmapStatusPill(status) {
    const st = status || "planned";
    const styles = {
      in_progress: "border-amber-500/40 bg-amber-500/10 text-amber-200",
      executed: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
      cancelled: "border-rose-500/40 bg-rose-500/10 text-rose-200",
      planned: "border-ink-600 bg-ink-800 text-mist-300",
    };
    const label =
      st === "in_progress" ? "in progress" : st === "executed" ? "executed" : st;
    return `<span class="inline-flex items-center rounded-md border px-2 py-0.5 text-xs uppercase tracking-[0.08em] ${styles[st] || styles.planned}">${escText(label)}</span>`;
  }

  /** Turn dense Stage N result prose into Metric/Value rows for a compact table. */
  function parseRoadmapResultRows(text) {
    const raw = String(text || "").trim();
    if (!raw) return { rows: [], leftover: "" };
    const rows = [];
    const seen = new Set();
    const labelMap = {
      oof: "OOF ROC-AUC",
      "oof roc-auc": "OOF ROC-AUC",
      "roc-auc": "OOF ROC-AUC",
      gap: "Train−Valid gap",
      pr: "OOF PR-AUC",
      "pr-auc": "OOF PR-AUC",
      brier: "OOF Brier",
      folds: "Fold AUCs",
      adv: "Adv AUC",
      "adv auc": "Adv AUC",
    };
    const skipKv = new Set([
      "auc",
      "random_state",
      "shuffle",
      "true",
      "false",
      "n_splits",
    ]);
    const push = (metric, value) => {
      let m = String(metric || "").trim();
      let v = String(value || "").trim();
      if (!m || !v) return;
      const mapped = labelMap[m.toLowerCase()];
      if (mapped) m = mapped;
      v = v.replace(/[;,\s]+$/g, "");
      if (!/[\]\)]$/.test(v)) v = v.replace(/\.+$/g, "");
      if (v.startsWith("[") && v.endsWith("]")) {
        v = v.replace(/,/g, ", ");
      }
      const key = m.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      rows.push({ metric: m, value: v });
    };
    const num = String.raw`[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][+-]?\d+)?`;

    // Named narrative first (Stage 1 / 2 / CONTROL), then remaining key=value tokens.
    const patterns = [
      [/\bCONTROL\s+(\S+)/i, "Control model"],
      [
        new RegExp(
          String.raw`OOF\s*ROC-?AUC\s*=\s*(${num})(?:\s*(\([^)]+\)))?`,
          "i"
        ),
        "OOF ROC-AUC",
        (m) => (m[2] ? `${m[1]} ${m[2]}` : m[1]),
      ],
      [new RegExp(String.raw`Adv\s*AUC\s*=\s*(${num})`, "i"), "Adv AUC"],
      [new RegExp(String.raw`OOF\s*Δ\s*=\s*(${num})`, "i"), "OOF Δ"],
      [/wins?\s+(\d+\s*\/\s*\d+)/i, "Fold wins"],
      [/gate\s+LOCKED:\s*([^.]+)/i, "Promotion gate"],
      [/Challenger\s+([^.]+?REJECTED(?:\s*\([^)]*\))?)/i, "Challenger"],
      [/baseline\s+(LGBM[^.;=]+?)(?=\s+OOF|\s*;|$)/i, "Baseline"],
      [/LOCKED\s+(StratifiedKFold\([^)]+\))/i, "CV lock"],
      [/(?:Artifact[:\s]+)?((?:logs|preds)\/[^\s+]+)/i, "Artifact"],
    ];
    patterns.forEach((entry) => {
      const re = entry[0];
      const label = entry[1];
      const pick = entry[2];
      const m = raw.match(re);
      if (!m) return;
      push(label, typeof pick === "function" ? pick(m) : m[1]);
    });

    const kvRe = new RegExp(
      String.raw`\b([A-Za-z][A-Za-z0-9_/-]{0,40})\s*=\s*(\[[^\]]*\]|${num}(?:\s*\([^)]+\))?)`,
      "g"
    );
    for (const m of raw.matchAll(kvRe)) {
      if (skipKv.has(m[1].toLowerCase())) continue;
      push(m[1], m[2]);
    }

    // Handbook steps only: "1.1 word" / "2.2 word" — never float scores like 0.949315.
    if (rows.length < 2) {
      raw.split(/(?=\b[1-9]\.\d{1,2}\s+[A-Za-z])/).forEach((chunk) => {
        const c = chunk.trim();
        if (!c) return;
        const head = c.match(/^([1-9]\.\d{1,2})\s+([A-Za-z].+)$/);
        if (head) push("Step " + head[1], head[2].replace(/\s+/g, " ").slice(0, 220));
      });
    }

    return { rows, leftover: rows.length ? "" : raw };
  }

  function roadmapResultTableHtml(result, resultMetric) {
    const parsed = parseRoadmapResultRows(result);
    const rows = parsed.rows.slice();
    if (resultMetric != null && !rows.some((r) => /roc-?auc|adv auc|metric/i.test(r.metric))) {
      rows.unshift({ metric: "Primary metric", value: fmtNum(resultMetric) });
    }
    const tableRows = rows
      .map(
        (r) => `<tr class="border-t border-ink-700">
        <th class="px-3 py-2 text-left text-xs font-medium text-mist-500 whitespace-nowrap">${escText(r.metric)}</th>
        <td class="px-3 py-2 text-sm tabular-nums text-signal">${escText(r.value)}</td>
      </tr>`
      )
      .join("");
    const summaryBits = rows
      .slice(0, 3)
      .map((r) => `${r.metric} ${r.value}`)
      .join(" · ");
    const summary =
      resultMetric != null
        ? `Result · ${fmtNum(resultMetric)}${rows.length ? " · " + rows.length + " fields" : ""}`
        : summaryBits || "Result details";
    const body = tableRows
      ? `<div class="mt-2 overflow-x-auto rounded-lg border border-ink-700">
          <table class="min-w-full text-left">
            <thead class="bg-ink-950 text-[10px] uppercase tracking-[0.1em] text-mist-500">
              <tr><th class="px-3 py-2">Metric</th><th class="px-3 py-2">Value</th></tr>
            </thead>
            <tbody>${tableRows}</tbody>
          </table>
        </div>`
      : `<p class="mt-2 whitespace-pre-wrap text-sm text-mist-200">${escText(parsed.leftover || result)}</p>`;
    return `<details class="mt-3 rounded-lg border border-ink-700 bg-ink-950/50 open:bg-ink-950">
      <summary class="cursor-pointer list-none px-3 py-2 text-sm text-mist-300 marker:content-none [&::-webkit-details-marker]:hidden">
        <span class="text-mist-500">▸</span> ${escText(summary)}
      </summary>
      <div class="border-t border-ink-700 px-3 pb-3 pt-2">
        ${body}
        ${
          tableRows
            ? `<details class="mt-3">
                <summary class="cursor-pointer text-xs text-mist-500">Raw notes</summary>
                <p class="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-mist-400">${escText(result)}</p>
              </details>`
            : ""
        }
      </div>
    </details>`;
  }

  function roadmapStrategyCard(s) {
    const st = s.status || "planned";
    const accent =
      st === "in_progress"
        ? "border-l-amber-400"
        : st === "executed"
          ? "border-l-emerald-400"
          : st === "cancelled"
            ? "border-l-rose-400"
            : "border-l-ink-600";
    const actions = [];
    if (st === "planned") {
      actions.push(
        `<button type="button" class="studio-ghost roadmap-start" data-id="${escText(s.id || "")}">Start</button>`
      );
    }
    if (st === "planned" || st === "in_progress") {
      actions.push(
        `<button type="button" class="studio-cta roadmap-done" data-id="${escText(s.id || "")}">Record result</button>`
      );
    }
    actions.push(
      `<button type="button" class="studio-link roadmap-delete" data-id="${escText(s.id || "")}">Remove</button>`
    );
    const plan = String(s.plan || "").trim();
    const result = String(s.result || "").trim();
    const metricHero =
      s.result_metric != null
        ? `<div class="mt-3 inline-flex min-w-[7rem] flex-col rounded-lg border border-ink-700 bg-ink-950 px-3 py-2">
            <div class="text-[10px] uppercase tracking-[0.12em] text-mist-500">Metric</div>
            <div class="text-2xl font-semibold tabular-nums text-signal">${fmtNum(s.result_metric)}</div>
          </div>`
        : "";
    const planBlock = plan
      ? `<details class="mt-3">
          <summary class="cursor-pointer text-xs uppercase tracking-[0.12em] text-mist-500">Plan</summary>
          <p class="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-mist-300">${escText(plan)}</p>
        </details>`
      : "";
    const resultBlock =
      result || s.result_metric != null
        ? `<div class="mt-3 border-t border-ink-700 pt-3">
            <div class="text-xs uppercase tracking-[0.12em] text-mist-500">Result</div>
            ${metricHero}
            ${result ? roadmapResultTableHtml(result, s.result_metric) : ""}
          </div>`
        : "";
    return `<article class="studio-card border-l-4 ${accent}" data-strategy="${escText(s.id || "")}">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0 flex-1">
          <h3 class="text-base font-semibold text-signal">${escText(s.title || "")}</h3>
          <p class="mt-1 text-xs text-mist-500">priority ${escText(String(s.priority != null ? s.priority : 100))}</p>
        </div>
        ${roadmapStatusPill(st)}
      </div>
      ${planBlock}
      ${resultBlock}
      <div class="mt-4 flex flex-wrap items-center gap-2">${actions.join("")}</div>
    </article>`;
  }

  /** Pull short takeaways from result prose (gates, rejects, prefers). */
  function extractRoadmapTakeaways(text) {
    const raw = String(text || "").replace(/\s+/g, " ").trim();
    if (!raw) return [];
    const out = [];
    const seen = new Set();
    const push = (s) => {
      const t = String(s || "")
        .replace(/\s+/g, " ")
        .trim()
        .replace(/[.;,\s]+$/g, "");
      if (!t || t.length < 12) return;
      const key = t.toLowerCase().slice(0, 80);
      if (seen.has(key)) return;
      seen.add(key);
      out.push(t.length > 220 ? t.slice(0, 217) + "…" : t);
    };
    const patterns = [
      /gate\s+LOCKED:\s*([^.]+)/i,
      /Challenger\s+[^.]+?REJECTED(?:\s*\([^)]*\))?/i,
      /Prefer\s+[^.]+/i,
      /Do not\s+[^.]+/i,
      /LOCKED\s+StratifiedKFold\([^)]+\)/i,
      /baseline\s+LGBM[^.;=]+/i,
      /OOF\s*Δ\s*=\s*[+-]?(?:\d+(?:\.\d+)?|\.\d+)/i,
      /wins?\s+\d+\s*\/\s*\d+/i,
    ];
    patterns.forEach((re) => {
      const m = raw.match(re);
      if (m) push(m[0]);
    });
    raw.split(/(?<=[.!?])\s+/).forEach((sent) => {
      if (/\b(prefer|reject|locked|gate|do not|failed|too slow|baseline)\b/i.test(sent)) {
        push(sent);
      }
    });
    return out.slice(0, 4);
  }

  function buildRoadmapConclusions(executed) {
    const items = (executed || [])
      .slice()
      .sort((a, b) => (a.priority || 100) - (b.priority || 100));
    const withMetric = items.filter((s) => s.result_metric != null && Number.isFinite(Number(s.result_metric)));
    const metrics = withMetric.map((s) => Number(s.result_metric));
    const stage2 = items.find((s) => /stage\s*2/i.test(s.title || ""));
    const lockedCv =
      stage2 && stage2.result_metric != null ? Number(stage2.result_metric) : null;
    const latest = withMetric.length ? withMetric[withMetric.length - 1] : null;
    const first = withMetric.length ? withMetric[0] : null;
    const delta =
      first && latest && withMetric.length > 1
        ? Number(latest.result_metric) - Number(first.result_metric)
        : null;
    const path =
      metrics.length > 1
        ? metrics.map((n) => fmtNum(n)).join(" → ")
        : metrics.length === 1
          ? fmtNum(metrics[0])
          : null;

    const trail = items
      .map((s) => {
        const parsed = parseRoadmapResultRows(s.result || "");
        const highlight = parsed.rows
          .filter((r) =>
            /roc-?auc|adv auc|fold wins|promotion gate|challenger|cv lock|oof Δ|baseline/i.test(
              r.metric
            )
          )
          .slice(0, 4);
        const takeaways = extractRoadmapTakeaways(s.result || "");
        const metric =
          s.result_metric != null
            ? `<span class="font-semibold tabular-nums text-signal">${fmtNum(s.result_metric)}</span>`
            : `<span class="text-mist-500">—</span>`;
        const facts = highlight.length
          ? `<ul class="mt-2 space-y-1">${highlight
              .map(
                (r) =>
                  `<li class="text-xs text-mist-400"><span class="text-mist-500">${escText(r.metric)}</span> · <span class="tabular-nums text-mist-200">${escText(r.value)}</span></li>`
              )
              .join("")}</ul>`
          : "";
        const notes = takeaways.length
          ? `<ul class="mt-2 list-disc space-y-1 pl-4 text-xs leading-relaxed text-mist-300">${takeaways
              .map((t) => `<li>${escText(t)}</li>`)
              .join("")}</ul>`
          : !facts && String(s.result || "").trim()
            ? `<p class="mt-2 text-xs leading-relaxed text-mist-400">${escText(
                String(s.result).trim().length > 180
                  ? String(s.result).trim().slice(0, 177) + "…"
                  : String(s.result).trim()
              )}</p>`
            : "";
        return `<li class="rounded-lg border border-ink-700 bg-ink-950/60 px-3 py-2">
          <div class="flex flex-wrap items-start justify-between gap-2">
            <div class="min-w-0 flex-1 text-sm font-medium text-signal">${escText(s.title || "")}</div>
            <div class="text-right">${metric}</div>
          </div>
          ${facts}
          ${notes}
        </li>`;
      })
      .join("");

    const conclusions = [];
    if (lockedCv != null) {
      conclusions.push(
        `Stage 2 locked CV harness at ${fmtNum(lockedCv)} — use as the reference baseline for later stages.`
      );
    }
    if (path && delta != null) {
      const dir = delta > 0 ? "up" : delta < 0 ? "down" : "flat";
      conclusions.push(
        `Primary metric path across ${withMetric.length} measured stages: ${path} (${dir} ${fmtNum(Math.abs(delta))} from first → latest).`
      );
    } else if (path) {
      conclusions.push(`Primary metric recorded: ${path}.`);
    }
    items.forEach((s) => {
      extractRoadmapTakeaways(s.result || "").forEach((t) => {
        if (!conclusions.some((c) => c.toLowerCase().includes(t.toLowerCase().slice(0, 40)))) {
          conclusions.push(`${s.title || "Stage"}: ${t}`);
        }
      });
    });
    const dead = (state.deadEndsList || []).filter(
      (d) => (d.status || "active_block") === "active_block"
    );
    dead.slice(0, 6).forEach((d) => {
      const lesson = String(d.lesson || "").trim();
      const short =
        lesson.length > 160 ? lesson.slice(0, 157) + "…" : lesson || "verified block";
      conclusions.push(`Dead end · ${d.variable || "var"}: ${short}`);
    });
    const active = (state.roadmapList || []).filter((s) => s.status === "in_progress");
    const nextBits = active.map((s) => s.title || "untitled").filter(Boolean);
    if (nextBits.length) {
      conclusions.push(`In progress next: ${nextBits.join("; ")}.`);
    } else {
      const planned = (state.roadmapList || []).filter(
        (s) => (s.status || "planned") === "planned"
      );
      if (planned.length) {
        const next = planned
          .slice()
          .sort((a, b) => (a.priority || 100) - (b.priority || 100))[0];
        conclusions.push(`No stage in progress — next planned: ${next.title || "untitled"}.`);
      }
    }

    const conclusionList = conclusions.length
      ? `<ul class="mt-2 list-disc space-y-2 pl-5 text-sm leading-relaxed text-mist-200">${conclusions
          .slice(0, 10)
          .map((c) => `<li>${escText(c)}</li>`)
          .join("")}</ul>`
      : `<p class="mt-2 text-sm text-mist-500">Not enough result text yet to draw conclusions.</p>`;

    const headlineBits = [
      `${items.length} executed`,
      lockedCv != null ? `locked CV ${fmtNum(lockedCv)}` : null,
      path ? `path ${path}` : null,
      dead.length ? `${dead.length} active dead end${dead.length === 1 ? "" : "s"}` : null,
    ].filter(Boolean);

    return `<section class="studio-card border-l-4 border-l-emerald-400" id="roadmap-summary-panel">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 class="text-base font-semibold text-signal">Summary &amp; conclusions</h3>
          <p class="mt-1 text-xs text-mist-500">${escText(headlineBits.join(" · ") || "From executed roadmap data")}</p>
        </div>
        <button type="button" class="studio-link" id="roadmap-hide-summary">Hide</button>
      </div>
      <div class="mt-4">
        <h4 class="text-[10px] uppercase tracking-[0.12em] text-mist-500">Stage trail</h4>
        <ul class="mt-2 space-y-2">${trail || `<li class="text-sm text-mist-500">No executed stages.</li>`}</ul>
      </div>
      <div class="mt-5 border-t border-ink-700 pt-4">
        <h4 class="text-[10px] uppercase tracking-[0.12em] text-mist-500">Conclusions so far</h4>
        ${conclusionList}
      </div>
    </section>`;
  }

  function roadmapExecutedBoard(items) {
    if (!items.length) {
      return `<p class="text-sm text-mist-500">Nothing executed yet.</p>`;
    }
    const open = !!state.roadmapSummaryOpen;
    const summaryBtn = `<button type="button" class="studio-ghost" id="roadmap-show-summary">${
      open ? "Hide summary" : "Summary & conclusions"
    }</button>`;
    const summaryPanel = open ? buildRoadmapConclusions(items) : "";
    return `<div class="space-y-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-xs font-medium uppercase tracking-[0.14em] text-mist-500">Executed · ${items.length}</h2>
        ${summaryBtn}
      </div>
      ${summaryPanel}
      <div class="grid gap-3">${items.map(roadmapStrategyCard).join("")}</div>
    </div>`;
  }

  function roadmapSection(title, items, emptyHint) {
    if (!items.length) {
      return `<p class="text-sm text-mist-500">${escText(emptyHint)}</p>`;
    }
    if (title === "Executed") {
      return roadmapExecutedBoard(items);
    }
    return `<div class="space-y-3">
      <h2 class="text-xs font-medium uppercase tracking-[0.14em] text-mist-500">${escText(title)} · ${items.length}</h2>
      <div class="grid gap-3">${items.map(roadmapStrategyCard).join("")}</div>
    </div>`;
  }

  function roadmapBody(project) {
    const list = state.roadmapList || [];
    const byStatus = {
      in_progress: list.filter((s) => s.status === "in_progress"),
      planned: list.filter((s) => (s.status || "planned") === "planned"),
      executed: list.filter((s) => s.status === "executed"),
      cancelled: list.filter((s) => s.status === "cancelled"),
    };
    Object.keys(byStatus).forEach((k) => {
      byStatus[k].sort((a, b) => (a.priority || 100) - (b.priority || 100));
    });
    const counts = {
      all: list.length,
      in_progress: byStatus.in_progress.length,
      planned: byStatus.planned.length,
      executed: byStatus.executed.length,
      cancelled: byStatus.cancelled.length,
    };
    const filter = state.roadmapFilter || "all";
    const tabs = [
      ["all", "All"],
      ["in_progress", "In progress"],
      ["planned", "Planned"],
      ["executed", "Executed"],
      ["cancelled", "Cancelled"],
    ]
      .map(([id, label]) => {
        const n = counts[id] || 0;
        const on = filter === id ? "studio-tab-on" : "";
        return `<button type="button" class="studio-tab ${on}" data-roadmap-filter="${id}" role="tab" aria-selected="${filter === id}">${label} <span class="text-mist-500">(${n})</span></button>`;
      })
      .join("");

    let board = "";
    if (filter === "all") {
      // Active + done first, backlog after — Stage results stay visible without digging.
      const chunks = [];
      if (byStatus.in_progress.length) {
        chunks.push(roadmapSection("In progress", byStatus.in_progress, ""));
      }
      if (byStatus.executed.length) {
        chunks.push(roadmapSection("Executed", byStatus.executed, ""));
      }
      if (byStatus.planned.length) {
        chunks.push(roadmapSection("Planned", byStatus.planned, ""));
      }
      if (byStatus.cancelled.length) {
        chunks.push(roadmapSection("Cancelled", byStatus.cancelled, ""));
      }
      board = chunks.length
        ? `<div class="space-y-8">${chunks.join("")}</div>`
        : `<p class="text-sm text-mist-500">No strategies yet. Add a planned approach below.</p>`;
    } else if (filter === "executed") {
      board = byStatus.executed.length
        ? roadmapExecutedBoard(byStatus.executed)
        : `<p class="text-sm text-mist-500">Nothing in this filter.</p>`;
    } else {
      const items = byStatus[filter] || [];
      board = items.length
        ? `<div class="grid gap-3">${items.map(roadmapStrategyCard).join("")}</div>`
        : `<p class="text-sm text-mist-500">Nothing in this filter.</p>`;
    }

    return `
${modeNav(project)}
<section class="page">
  <div class="mb-6 flex flex-wrap items-end justify-between gap-4">
    <div>
      <h1 class="text-3xl font-semibold tracking-tight text-signal">Roadmap</h1>
      <p class="mt-1 text-sm text-mist-400">Plan → run → record. Status tabs separate the queue from done work.</p>
    </div>
  </div>
  <div class="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
    ${stat("In progress", String(counts.in_progress))}
    ${stat("Planned", String(counts.planned))}
    ${stat("Executed", String(counts.executed))}
    ${stat("Total", String(counts.all))}
  </div>
  <div class="mb-6 flex flex-wrap items-center gap-2" role="tablist" aria-label="Roadmap status filter">
    ${tabs}
  </div>
  <div class="mb-8">${board}</div>
  <section class="studio-card max-w-xl">
    <h2 class="text-lg font-medium text-signal">Add strategy</h2>
    <label class="studio-label" for="roadmap-title">Title</label>
    <input class="studio-input" id="roadmap-title" placeholder="e.g. Stage 2 — Master CV harness" />
    <label class="studio-label" for="roadmap-plan">Plan</label>
    <textarea class="studio-input" id="roadmap-plan" rows="4" placeholder="What you will try and why"></textarea>
    <label class="studio-label" for="roadmap-priority">Priority (lower = earlier)</label>
    <input class="studio-input" id="roadmap-priority" type="number" value="100" />
    <div class="mt-4">
      <button type="button" class="studio-cta" id="roadmap-create">Add to roadmap</button>
    </div>
  </section>
  <dialog id="roadmap-result-dialog" class="rounded-xl border border-ink-600 bg-ink-900 p-4 text-mist-200 shadow-card backdrop:bg-zinc-900/25">
    <form method="dialog" class="space-y-2">
      <h2 class="text-lg font-medium text-signal">Record result</h2>
      <input type="hidden" id="roadmap-result-id" value="" />
      <label class="studio-label" for="roadmap-result-text">Result</label>
      <textarea class="studio-input" id="roadmap-result-text" rows="4" placeholder="What happened — CV / public / lesson"></textarea>
      <label class="studio-label" for="roadmap-result-metric">Metric (optional)</label>
      <input class="studio-input" id="roadmap-result-metric" type="number" step="any" placeholder="e.g. 0.5008" />
      <div class="flex gap-2 pt-2">
        <button type="submit" class="studio-cta" id="roadmap-result-save" value="save">Mark executed</button>
        <button type="submit" class="studio-ghost" value="cancel">Cancel</button>
      </div>
    </form>
  </dialog>
</section>`;
  }

  function sourcesBody(project) {
    const list = state.sourcesList || [];
    const rows = list
      .map(
        (s) => `<tr>
      <td><a class="studio-link" href="${escText(s.url || "")}" target="_blank" rel="noopener noreferrer">${escText(s.title || "")}</a></td>
      <td class="sub"><a class="studio-link" href="${escText(s.url || "")}" target="_blank" rel="noopener noreferrer">${escText(s.url || "")}</a></td>
      <td>${escText(s.description || "")}</td>
      <td class="actions">
        <button type="button" class="linkish source-delete" data-id="${escText(s.id || "")}">[ remove ]</button>
      </td>
    </tr>`
      )
      .join("");
    return `
${modeNav(project)}
<section class="page">
  <div class="page-head">
    <div>
      <h1>Sources</h1>
      <p class="lede">Links you keep for this project — papers, notebooks, datasets, write-ups.</p>
    </div>
  </div>
  <div class="stats">
    ${stat("Sources", String(list.length))}
  </div>
  <section class="card span2">
    <h2>Saved sources</h2>
    ${
      rows
        ? `<table><thead><tr><th>Title</th><th>URL</th><th>Description</th><th></th></tr></thead><tbody>${rows}</tbody></table>`
        : `<p class="sub">No sources yet. Add a link below.</p>`
    }
  </section>
  <section class="card">
    <h2>Add source</h2>
    <label for="source-title">Title</label>
    <input id="source-title" placeholder="e.g. Winning solution write-up" />
    <label for="source-url">URL</label>
    <input id="source-url" type="url" placeholder="https://…" />
    <label for="source-desc">Description</label>
    <textarea id="source-desc" rows="3" placeholder="Why this matters for the campaign"></textarea>
    <button type="button" class="cta" id="source-create">Add source</button>
  </section>
</section>`;
  }

  function deadEndStatusPill(status) {
    const st = status || "active_block";
    const styles =
      st === "needs_reverification"
        ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
        : "border-rose-500/40 bg-rose-500/10 text-rose-200";
    const label =
      st === "needs_reverification" ? "needs reverify" : "active block";
    return `<span class="inline-flex items-center rounded-md border px-2 py-0.5 text-xs uppercase tracking-[0.08em] ${styles}">${escText(label)}</span>`;
  }

  function deadEndCard(d) {
    const st = d.status || "active_block";
    const accent =
      st === "needs_reverification" ? "border-l-amber-400" : "border-l-rose-400";
    const lesson = String(d.lesson || "").trim();
    const short =
      lesson.length > 140 ? lesson.slice(0, 137) + "…" : lesson || "No lesson recorded";
    return `<article class="studio-card border-l-4 ${accent}">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0 flex-1">
          <h3 class="break-words font-mono text-sm font-semibold text-signal">${escText(d.variable || "")}</h3>
          <p class="mt-1 text-xs text-mist-500">epoch ${escText(d.epoch_id || "—")} · cited ${escText(String(d.times_cited ?? 0))} · retrieved ${escText(String(d.times_retrieved ?? 0))}</p>
        </div>
        ${deadEndStatusPill(st)}
      </div>
      <details class="mt-3">
        <summary class="cursor-pointer text-sm text-mist-300 marker:content-none [&::-webkit-details-marker]:hidden">
          <span class="text-mist-500">▸</span> ${escText(short)}
        </summary>
        <p class="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-mist-200">${escText(lesson || "—")}</p>
      </details>
    </article>`;
  }

  function deadEndsBody(project, dash) {
    const panel = (dash && dash.dead_ends) || {};
    const list = state.deadEndsList || [];
    const active = list.filter((d) => (d.status || "active_block") === "active_block");
    const reverify = list.filter((d) => d.status === "needs_reverification");
    const filter = state.deadEndsFilter || "all";
    const filtered =
      filter === "active_block"
        ? active
        : filter === "needs_reverification"
          ? reverify
          : list.slice();
    const tabs = [
      ["all", "All", list.length],
      ["active_block", "Active blocks", active.length],
      ["needs_reverification", "Needs reverify", reverify.length],
    ]
      .map(([id, label, n]) => {
        const on = filter === id ? "studio-tab-on" : "";
        return `<button type="button" class="studio-tab ${on}" data-dead-filter="${id}" role="tab" aria-selected="${filter === id}">${label} <span class="text-mist-500">(${n})</span></button>`;
      })
      .join("");
    const topVars = (panel.top_variables || list.map((d) => d.variable).filter(Boolean)).slice(0, 6);
    const topPills = topVars.length
      ? topVars
          .map(
            (v) =>
              `<span class="inline-flex max-w-full break-all rounded-md border border-ink-600 bg-ink-800 px-2 py-1 font-mono text-xs text-mist-300">${escText(v)}</span>`
          )
          .join("")
      : `<span class="text-sm text-mist-500">None yet</span>`;
    const board = filtered.length
      ? `<div class="grid gap-3">${filtered.map(deadEndCard).join("")}</div>`
      : `<p class="text-sm text-mist-500">No dead ends in this filter.</p>`;
    return `
${modeNav(project)}
<section class="page">
  <div class="mb-6 flex flex-wrap items-end justify-between gap-4">
    <div>
      <h1 class="text-3xl font-semibold tracking-tight text-signal">Dead ends</h1>
      <p class="mt-1 text-sm text-mist-400">Blocked strategies with verified lessons — do not reopen without a new plan.</p>
    </div>
  </div>
  <div class="mb-6 grid gap-3 sm:grid-cols-3">
    ${stat("Total", String(list.length || panel.count || 0))}
    ${stat("Active blocks", String(active.length))}
    ${stat("Needs reverify", String(reverify.length))}
  </div>
  <section class="studio-card mb-6">
    <h2 class="mb-3 text-sm font-medium text-signal">Top variables</h2>
    <div class="flex flex-wrap gap-2">${topPills}</div>
  </section>
  <div class="mb-6 flex flex-wrap items-center gap-2" role="tablist" aria-label="Dead end status filter">
    ${tabs}
  </div>
  <div class="mb-8">${board}</div>
  <section class="studio-card max-w-xl">
    <h2 class="text-lg font-medium text-signal">Record dead end</h2>
    <label class="studio-label" for="dead-var">Strategy / variable</label>
    <input class="studio-input" id="dead-var" placeholder="e.g. lgbm_max_depth_8_num_leaves_63" />
    <label class="studio-label" for="dead-lesson">Lesson</label>
    <textarea class="studio-input" id="dead-lesson" rows="4" placeholder="What was verified and why this path stays blocked"></textarea>
    <label class="studio-label" for="dead-status">Status</label>
    <select class="studio-input" id="dead-status">
      <option value="active_block">Active block</option>
      <option value="needs_reverification">Needs reverify</option>
    </select>
    <div class="mt-4">
      <button type="button" class="studio-cta" id="dead-create">Save dead end</button>
    </div>
  </section>
</section>`;
  }

  function labBody(project, dash) {
    const levers = (dash && dash.levers) || {};
    const flags = ((state.me || {}).org || {}).feature_flags || {};
    const ap = state.autopilot || {};
    const session = ap.session || {};
    const leverRows = (state.leversList || [])
      .map(
        (L) => `<tr>
      <td>${escText(L.variable || "")}</td>
      <td>${escText(L.status || "")}</td>
      <td>${fmtNum(L.cv_mean)}</td>
      <td>${escText(L.verdict || "—")}</td>
      <td>${L.status === "open" ? `<button type="button" class="linkish lever-close" data-id="${escText(L.id)}">[ close ]</button>` : ""}</td>
    </tr>`
      )
      .join("");
    const digest = state.nightDigest;
    return `
${modeNav(project)}
<section class="page">
  <div class="page-head">
    <div>
      <h1>Lab</h1>
      <p class="lede">Research · Levers · Ensemble · Night-Shift. Autopilot never auto-submits to Kaggle.</p>
    </div>
    <button type="button" class="cta" id="ap-start">Start night shift</button>
  </div>
  <div class="stats">
    ${stat("Open levers", String(levers.open || 0))}
    ${stat("Closed", String(levers.closed || 0))}
    ${stat("Kills", String(levers.kills || 0))}
    ${stat("Promotes", String(levers.promotes || 0))}
  </div>
  <div class="grid">
    <section class="card">
      <h2>Research run</h2>
      <p class="sub">POST /research-runs · fold0_smoke default</p>
      <button type="button" class="ghost" id="research-run">Queue fold0 smoke</button>
      ${state.researchLast ? `<p class="sub">Last ${escText(state.researchLast.run_id || "")} · ${escText(state.researchLast.status || "")}</p>` : ""}
    </section>
    <section class="card">
      <h2>Ensemble</h2>
      <p class="sub">Plan blend from OOF ids (comma-separated)</p>
      <input id="ensemble-oofs" placeholder="oof_…" />
      <button type="button" class="ghost" id="ensemble-run">Optimize / plan</button>
      ${state.ensembleLast ? `<pre class="board mini">${escText(state.ensembleLast.ascii_board || state.ensembleLast.message || state.ensembleLast.status || "")}</pre>` : ""}
    </section>
    <section class="card span2">
      <h2>Levers</h2>
      ${leverRows ? `<table><thead><tr><th>Variable</th><th>Status</th><th>CV</th><th>Verdict</th><th></th></tr></thead><tbody>${leverRows}</tbody></table>` : `<p class="sub">No levers.</p>`}
      <p class="sec-actions"><button type="button" class="linkish" id="lab-open-lever">[ open lever ]</button></p>
    </section>
    <section class="card span2">
      <h2>Night shift</h2>
      <p>${escText(ap.status || ap.message || "No session")}${session.id ? ` · ${escText(session.id)}` : ""}</p>
      <p class="sub">flag night_shift=${flags.night_shift ? "on" : "off"} · auto_kaggle_submit=false</p>
      <p class="sec-actions">
        <button type="button" class="linkish" id="ap-pause">[ pause ]</button>
        <button type="button" class="linkish" id="ap-resume">[ resume ]</button>
        <button type="button" class="linkish" id="ap-digest">[ morning digest ]</button>
        <button type="button" class="linkish" id="ap-halt">[ halt ]</button>
      </p>
      ${digest && digest.ascii_board ? `<pre class="board">${escText(digest.ascii_board)}</pre>` : ""}
    </section>
  </div>
</section>`;
  }

  function kaggleBody(project) {
    if (!project || project.kind !== "kaggle") {
      return `${modeNav(project)}<section class="page"><h1>Kaggle</h1><p class="lede">Hidden for standalone projects.</p></section>`;
    }
    const intel = state.intel || {};
    const discussions = (intel.discussions || []).slice(0, 8);
    const kernels = (intel.kernels || []).slice(0, 8);
    const submissions = (intel.submissions || []).slice(0, 8);
    return `
${modeNav(project)}
<section class="page">
  <div class="page-head">
    <div>
      <h1>Kaggle</h1>
      <p class="lede">${escText(intel.competition || "competition")} · refresh ${escText(String(intel.refreshed_by || intel.last_sync || "not yet"))}</p>
    </div>
    <button type="button" class="cta" id="kaggle-sync">Sync now</button>
  </div>
  <div class="stats">
    ${stat("Rank", String(intel.rank ?? intel.position ?? "—"))}
    ${stat("Public", fmtNum(intel.public_score))}
    ${stat("Files", String((intel.files || []).length || "—"))}
    ${stat("Sync", intel.error ? "error" : (intel.refreshed_by || "idle"))}
  </div>
  <p class="sec-actions">
    <button type="button" class="linkish" id="kaggle-import">[ import competition data ]</button>
    <button type="button" class="linkish" id="kaggle-diff">[ distribution diff stub ]</button>
    <button type="button" class="linkish" id="kaggle-package">[ package submission ]</button>
    <button type="button" class="linkish" id="kaggle-push">[ gated push ]</button>
  </p>
  <div class="grid">
    <section class="card"><h2>Competition files</h2>${(intel.files || []).length ? `<ul class="plain">${(intel.files || []).slice(0, 12).map((f) => `<li>${escText(f.name || "?")} · ${escText(String(f.total_bytes ?? f.totalBytes ?? ""))}</li>`).join("")}</ul>` : `<p class="sub">No file inventory yet — Sync now or Import data.</p>`}</section>
    <section class="card"><h2>Important discussions</h2>${discussions.length ? `<ul class="plain">${discussions.map((d) => `<li>${escText(d.title || d.text || d.id || "thread")}</li>`).join("")}</ul>` : `<p class="sub">No cached discussions.</p>`}</section>
    <section class="card"><h2>Public notebooks</h2>${kernels.length ? `<ul class="plain">${kernels.map((k) => `<li>${escText(k.title || k.ref || "kernel")}</li>`).join("")}</ul>` : `<p class="sub">No cached kernels.</p>`}</section>
    <section class="card"><h2>Sync health</h2><p class="sub">${escText(intel.error || "Live sync uses KAGGLE_API_TOKEN / sealed project token.")}</p>
      <label for="disc-text">Save discussion takeaway</label>
      <textarea id="disc-text" rows="3" placeholder="Paste thread signal"></textarea>
      <button type="button" class="ghost" id="kaggle-discussion">Ingest discussion</button>
    </section>
  </div>
</section>`;
  }

  function opsBody(project) {
    const accounts = Array.isArray(state.accounts) ? state.accounts : [];
    const err = state.accounts && state.accounts.error;
    const runners = Array.isArray(state.runners) ? state.runners : [];
    const runnerErr = state.runners && state.runners.error;
    const rows = accounts
      .map((a) => `<tr><td>${escText(a.provider || a.kind || "cloud")}</td><td>${escText(a.status || a.id || "")}</td></tr>`)
      .join("");
    const runnerRows = runners
      .map(
        (r) => `<tr>
      <td>${escText(r.runner_id || r.id || "")}</td>
      <td>${escText(r.kind || "")}</td>
      <td>${escText(r.status || "")}</td>
      <td>${escText(r.gpu_type || "")}</td>
      <td class="actions">
        <button type="button" class="linkish runner-stop" data-id="${escText(r.runner_id || "")}">[ stop ]</button>
        <button type="button" class="linkish runner-term" data-id="${escText(r.runner_id || "")}">[ terminate ]</button>
      </td>
    </tr>`
      )
      .join("");
    const mcpUrl = "http://127.0.0.1:8100/mcp";
    const gpus = Array.isArray(state.gpus) ? state.gpus : [];
    const gaps = Array.isArray(state.mcpGaps) ? state.mcpGaps : [];
    const gapRows = gaps
      .slice(0, 12)
      .map(
        (g) => `<tr>
      <td><span class="pill">${escText(g.severity || "")}</span></td>
      <td>${escText(g.title || "")}</td>
      <td class="sub">${escText(g.needed_capability || "")}</td>
      <td class="sub">${escText(g.suggested_tool_name || "—")}</td>
      <td class="sub">${escText(g.status || "open")}</td>
    </tr>`
      )
      .join("");
    return `
${modeNav(project)}
<section class="page">
  <div class="page-head">
    <div>
      <h1>Ops</h1>
      <p class="lede">Agents / MCP · Runners · Cloud · Git</p>
    </div>
  </div>
  <div class="grid">
    <section class="card span2">
      <h2>Agent / MCP connect</h2>
      <pre class="board mini">MCP endpoint: ${escText(mcpUrl)}
Auth: Authorization Bearer &lt;PAT&gt; from Settings (mcp:worker)
Never put JWT/PAT in SSE query strings.
Claim/complete stay MCP-primary; Overview shows mission status.</pre>
      <p class="sub">Mint a PAT under Settings → Agent connect, paste the follow-up into the running agent chat.</p>
    </section>
    <section class="card span2">
      <h2>MCP gaps (agent suggestions)</h2>
      <p class="sub">From tool <code>report_mcp_gap</code> — missing calls the agent hit while syncing.</p>
      ${
        gapRows
          ? `<table><thead><tr><th>Severity</th><th>Title</th><th>Needed</th><th>Suggested tool</th><th>Status</th></tr></thead><tbody>${gapRows}</tbody></table>`
          : `<p class="sub">No gap reports yet.</p>`
      }
    </section>
    <section class="card">
      <h2>Cloud accounts</h2>
      ${err ? `<p class="sub">${escText(err)}</p>` : rows ? `<table><thead><tr><th>Provider</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>` : `<p class="sub">No account connected.</p>`}
      <label for="runpod-key">RunPod API key</label>
      <input id="runpod-key" type="password" placeholder="rpa_…" />
      <button type="button" class="ghost" id="connect-runpod">Connect RunPod</button>
      <label for="aws-role">AWS role ARN</label>
      <input id="aws-role" placeholder="arn:aws:iam::…" />
      <button type="button" class="ghost" id="connect-aws">Connect AWS</button>
    </section>
    <section class="card">
      <h2>GPUs / quote / launch</h2>
      <button type="button" class="ghost" id="list-gpus">List RunPod GPUs</button>
      ${gpus.length ? `<ul class="plain">${gpus.slice(0, 6).map((g) => `<li>${escText(g.gpu_type)} · $${((g.cost_estimate_micros_hr || 0) / 1e6).toFixed(3)}/hr <button type="button" class="linkish quote-gpu" data-type="${escText(g.gpu_type)}" data-cost="${g.cost_estimate_micros_hr}">[ quote+launch ]</button></li>`).join("")}</ul>` : `<p class="sub">Quote before first provision.</p>`}
      ${state.quote ? `<p class="sub">Quote ${escText(state.quote.gpu_type)} · within entitlement ${state.quote.within_entitlement}</p>` : ""}
    </section>
    <section class="card span2">
      <h2>Runners</h2>
      ${runnerErr ? `<p class="sub">${escText(runnerErr)}</p>` : runnerRows ? `<table><thead><tr><th>Id</th><th>Kind</th><th>Status</th><th>GPU</th><th></th></tr></thead><tbody>${runnerRows}</tbody></table>` : `<p class="sub">No runners.</p>`}
    </section>
    <section class="card span2">
      <h2>Git</h2>
      <p class="sub">POST /git/plan — GitHub App install id or PAT fallback</p>
      <input id="git-install" placeholder="installation_id (optional)" />
      <button type="button" class="ghost" id="git-plan">Plan git sync</button>
      ${state.gitPlan ? `<pre class="board mini">${escText(JSON.stringify(state.gitPlan, null, 0).slice(0, 400))}</pre>` : ""}
    </section>
  </div>
</section>`;
  }

  function trustBody(project) {
    const members = state.members || [];
    const memberRows = members
      .map((m) => `<tr><td>${escText(m.email)}</td><td>${escText(m.role)}</td><td>${escText(m.status)}</td></tr>`)
      .join("");
    return `
${modeNav(project)}
<section class="page">
  <div class="page-head">
    <div>
      <h1>Trust</h1>
      <p class="lede">Credits harvest/verify/export · Members · redacted share</p>
    </div>
    <button type="button" class="cta" id="share">Publish snapshot</button>
  </div>
  <div class="grid">
    <section class="card">
      <h2>Credits</h2>
      <label for="credit-source">Source / asset ref</label>
      <input id="credit-source" placeholder="hf://… or kaggle://…" />
      <button type="button" class="ghost" id="credits-harvest">Harvest</button>
      <button type="button" class="ghost" id="credits-verify">Verify (kaggle_submit gate)</button>
      <button type="button" class="ghost" id="credits-export">Export bundle</button>
      ${state.creditsBoard ? `<pre class="board mini">${escText(state.creditsBoard.ascii_board || JSON.stringify(state.creditsBoard).slice(0, 360))}</pre>` : `<p class="sub">No harvest yet.</p>`}
    </section>
    <section class="card">
      <h2>Members</h2>
      ${memberRows ? `<table><thead><tr><th>Email</th><th>Role</th><th>Status</th></tr></thead><tbody>${memberRows}</tbody></table>` : `<p class="sub">No invites yet.</p>`}
      <div class="invite-row">
        <input id="trust-invite-email" placeholder="member@…" />
        <button type="button" class="ghost" id="trust-invite">Invite</button>
      </div>
    </section>
    <section class="card span2">
      <h2>Share</h2>
      <p class="sub">Publishes redacted PLG snapshot (goals + lever stats; dead-end lessons off by default).</p>
    </section>
  </div>
</section>`;
  }

  async function rerenderMode(force) {
    try {
      if (force) await refreshDashboard();
      state.modeDataFor = null;
      await loadModeData(true);
      state.error = "";
    } catch (e) {
      state.error = String(e.message || e);
    }
    renderProject();
  }

  function bindBrainActions() {
    const assign = document.getElementById("assign");
    if (assign) {
      assign.onclick = async () => {
        assign.disabled = true;
        try {
          state.advise = await api("/v1/projects/" + pid() + "/advise", {
            method: "POST",
            body: JSON.stringify({
              project_id: pid(),
              task: "next experiment",
              max_missions: 3,
            }),
          });
          await rerenderMode(true);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    const gotoKaggle = document.getElementById("goto-kaggle");
    if (gotoKaggle) {
      gotoKaggle.onclick = () => {
        state.mode = "KAGGLE";
        setRoute("studio/" + pid() + "/kaggle");
      };
    }
    const gotoRoadmap = document.getElementById("goto-roadmap");
    if (gotoRoadmap) {
      gotoRoadmap.onclick = () => {
        state.mode = "ROADMAP";
        state.roadmapFilter = "executed";
        setRoute("studio/" + pid() + "/roadmap");
      };
    }
    const syncGit = document.getElementById("sync-git");
    if (syncGit) {
      syncGit.onclick = async () => {
        try {
          state.gitPlan = await api("/v1/projects/" + pid() + "/git/plan", {
            method: "POST",
            body: JSON.stringify({ pat_fallback: true, mission_id: "" }),
          });
          state.notice = "Git plan ready (" + (state.gitPlan.auth || "ok") + ")";
          state.mode = "OPS";
          setRoute("studio/" + pid() + "/ops");
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    const progBtn = document.getElementById("record-progress");
    const progDlg = document.getElementById("progress-dialog");
    if (progBtn && progDlg) {
      progBtn.onclick = () => progDlg.showModal();
      document.getElementById("progress-save").onclick = async (ev) => {
        ev.preventDefault();
        const note = (document.getElementById("progress-note").value || "").trim();
        if (!note) return;
        try {
          await api("/v1/projects/" + pid() + "/progress", {
            method: "POST",
            body: JSON.stringify({ note }),
          });
          progDlg.close();
          state.notice = "Progress noted";
          await rerenderMode(true);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    const openLever = document.getElementById("open-lever");
    const leverDlg = document.getElementById("lever-dialog");
    if (openLever && leverDlg) {
      openLever.onclick = () => leverDlg.showModal();
      document.getElementById("lever-save").onclick = async (ev) => {
        ev.preventDefault();
        try {
          await api("/v1/projects/" + pid() + "/levers", {
            method: "POST",
            body: JSON.stringify({
              goal_id: document.getElementById("lever-goal").value.trim(),
              variable: document.getElementById("lever-var").value.trim() || "probe",
              band_low: Number(document.getElementById("lever-low").value || 0),
              band_high: Number(document.getElementById("lever-high").value || 0.05),
            }),
          });
          leverDlg.close();
          state.notice = "Lever opened";
          await rerenderMode(true);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    const closeLever = document.getElementById("close-lever");
    if (closeLever) {
      closeLever.onclick = async () => {
        try {
          await api("/v1/projects/" + pid() + "/levers/" + closeLever.getAttribute("data-id") + "/close", {
            method: "POST",
            body: JSON.stringify({ verdict: "kill", notes: "closed from overview" }),
          });
          state.notice = "Lever closed";
          await rerenderMode(true);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
  }

  function bindDeadEndsActions() {
    document.querySelectorAll("[data-dead-filter]").forEach((el) => {
      el.onclick = () => {
        state.deadEndsFilter = el.getAttribute("data-dead-filter") || "all";
        renderProject();
      };
    });
    const create = document.getElementById("dead-create");
    if (create) {
      create.onclick = async () => {
        const variable = (document.getElementById("dead-var").value || "").trim();
        const lesson = (document.getElementById("dead-lesson").value || "").trim();
        const status = document.getElementById("dead-status").value || "active_block";
        if (!variable || !lesson) {
          state.error = "variable and lesson required";
          renderProject();
          return;
        }
        try {
          await api("/v1/projects/" + pid() + "/dead-ends", {
            method: "POST",
            body: JSON.stringify({ variable, lesson, status }),
          });
          state.notice = "Dead end recorded";
          state.deadEndsFilter =
            status === "needs_reverification" ? "needs_reverification" : "active_block";
          document.getElementById("dead-var").value = "";
          document.getElementById("dead-lesson").value = "";
          await rerenderMode(true);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
  }

  function bindGitActions() {
    const link = document.getElementById("git-link");
    if (link) {
      link.onclick = async () => {
        const remote = (document.getElementById("git-remote").value || "").trim();
        if (!remote) {
          state.error = "git remote required";
          renderProject();
          return;
        }
        try {
          state.gitInfo = await api("/v1/projects/" + pid() + "/git", {
            method: "PUT",
            body: JSON.stringify({ remote, refresh: true }),
          });
          state.notice = "Git repository linked";
          state.error = "";
          await rerenderMode(true);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    const refresh = document.getElementById("git-refresh");
    if (refresh) {
      refresh.onclick = async () => {
        try {
          state.gitInfo = await api("/v1/projects/" + pid() + "/git/refresh", {
            method: "POST",
            body: JSON.stringify({}),
          });
          state.notice = "Git stats refreshed";
          await rerenderMode(true);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    const unlink = document.getElementById("git-unlink");
    if (unlink) {
      unlink.onclick = async () => {
        if (!window.confirm("Unlink this git repository from the project?")) return;
        try {
          state.gitInfo = await api("/v1/projects/" + pid() + "/git", {
            method: "DELETE",
          });
          state.notice = "Git repository unlinked";
          await rerenderMode(true);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
  }

  function bindRoadmapActions() {
    document.querySelectorAll("[data-roadmap-filter]").forEach((el) => {
      el.onclick = () => {
        state.roadmapFilter = el.getAttribute("data-roadmap-filter") || "all";
        renderProject();
      };
    });
    const showSummary = document.getElementById("roadmap-show-summary");
    if (showSummary) {
      showSummary.onclick = () => {
        state.roadmapSummaryOpen = !state.roadmapSummaryOpen;
        renderProject();
        if (state.roadmapSummaryOpen) {
          const panel = document.getElementById("roadmap-summary-panel");
          if (panel) panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      };
    }
    const hideSummary = document.getElementById("roadmap-hide-summary");
    if (hideSummary) {
      hideSummary.onclick = () => {
        state.roadmapSummaryOpen = false;
        renderProject();
      };
    }
    const create = document.getElementById("roadmap-create");
    if (create) {
      create.onclick = async () => {
        const title = (document.getElementById("roadmap-title").value || "").trim();
        const plan = (document.getElementById("roadmap-plan").value || "").trim();
        const priority = Number(document.getElementById("roadmap-priority").value || 100);
        if (!title || !plan) {
          state.error = "title and plan required";
          renderProject();
          return;
        }
        try {
          await api("/v1/projects/" + pid() + "/roadmap", {
            method: "POST",
            body: JSON.stringify({ title, plan, priority, status: "planned" }),
          });
          state.notice = "Strategy added to roadmap";
          state.roadmapFilter = "planned";
          document.getElementById("roadmap-title").value = "";
          document.getElementById("roadmap-plan").value = "";
          await rerenderMode(true);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    document.querySelectorAll(".roadmap-start").forEach((btn) => {
      btn.onclick = async () => {
        const id = btn.getAttribute("data-id");
        if (!id) return;
        try {
          await api("/v1/projects/" + pid() + "/roadmap/" + encodeURIComponent(id), {
            method: "PATCH",
            body: JSON.stringify({ status: "in_progress" }),
          });
          state.notice = "Strategy marked in progress";
          state.roadmapFilter = "in_progress";
          await rerenderMode(true);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    });
    document.querySelectorAll(".roadmap-done").forEach((btn) => {
      btn.onclick = () => {
        const id = btn.getAttribute("data-id");
        const dlg = document.getElementById("roadmap-result-dialog");
        const hid = document.getElementById("roadmap-result-id");
        if (!id || !dlg || !hid) return;
        hid.value = id;
        document.getElementById("roadmap-result-text").value = "";
        document.getElementById("roadmap-result-metric").value = "";
        dlg.showModal();
      };
    });
    const save = document.getElementById("roadmap-result-save");
    if (save) {
      save.onclick = async (ev) => {
        ev.preventDefault();
        const id = (document.getElementById("roadmap-result-id").value || "").trim();
        const result = (document.getElementById("roadmap-result-text").value || "").trim();
        const metricRaw = (document.getElementById("roadmap-result-metric").value || "").trim();
        if (!id || !result) {
          state.error = "result text required";
          renderProject();
          return;
        }
        const body = { status: "executed", result };
        if (metricRaw !== "" && !Number.isNaN(Number(metricRaw))) {
          body.result_metric = Number(metricRaw);
        }
        try {
          await api("/v1/projects/" + pid() + "/roadmap/" + encodeURIComponent(id), {
            method: "PATCH",
            body: JSON.stringify(body),
          });
          document.getElementById("roadmap-result-dialog").close();
          state.notice = "Strategy marked executed";
          state.roadmapFilter = "executed";
          await rerenderMode(true);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    document.querySelectorAll(".roadmap-delete").forEach((btn) => {
      btn.onclick = async () => {
        const id = btn.getAttribute("data-id");
        if (!id) return;
        try {
          await api("/v1/projects/" + pid() + "/roadmap/" + encodeURIComponent(id), {
            method: "DELETE",
          });
          state.notice = "Strategy removed";
          await rerenderMode(true);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    });
  }

  function bindSourcesActions() {
    const create = document.getElementById("source-create");
    if (create) {
      create.onclick = async () => {
        const title = (document.getElementById("source-title").value || "").trim();
        const url = (document.getElementById("source-url").value || "").trim();
        const description = (document.getElementById("source-desc").value || "").trim();
        if (!title || !url) {
          state.error = "title and url required";
          renderProject();
          return;
        }
        try {
          await api("/v1/projects/" + pid() + "/sources", {
            method: "POST",
            body: JSON.stringify({ title, url, description }),
          });
          state.notice = "Source added";
          document.getElementById("source-title").value = "";
          document.getElementById("source-url").value = "";
          document.getElementById("source-desc").value = "";
          await rerenderMode(true);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    document.querySelectorAll(".source-delete").forEach((btn) => {
      btn.onclick = async () => {
        const id = btn.getAttribute("data-id");
        if (!id) return;
        try {
          await api("/v1/projects/" + pid() + "/sources/" + encodeURIComponent(id), {
            method: "DELETE",
          });
          state.notice = "Source removed";
          await rerenderMode(true);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    });
  }

  function bindGoalsActions() {
    const create = document.getElementById("goal-create");
    if (create) {
      create.onclick = async () => {
        try {
          await api("/v1/projects/" + pid() + "/goals", {
            method: "POST",
            body: JSON.stringify({
              title: document.getElementById("goal-title").value.trim() || "Goal",
              kind: document.getElementById("goal-kind").value,
              metric_key: document.getElementById("goal-metric").value.trim() || "cv_mean",
              threshold: Number(document.getElementById("goal-thr").value || 0.3),
              direction: "maximize",
            }),
          });
          state.notice = "Goal created";
          await rerenderMode(true);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    document.querySelectorAll(".goal-met, .goal-abandon").forEach((el) => {
      el.onclick = async () => {
        const status = el.classList.contains("goal-met") ? "met" : "abandoned";
        try {
          await api("/v1/projects/" + pid() + "/goals/" + el.getAttribute("data-id"), {
            method: "PATCH",
            body: JSON.stringify({ status }),
          });
          state.notice = "Goal " + status;
          await rerenderMode(true);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    });
  }

  function bindLabActions() {
    const research = document.getElementById("research-run");
    if (research) {
      research.onclick = async () => {
        try {
          state.researchLast = await api("/v1/projects/" + pid() + "/research-runs", {
            method: "POST",
            body: JSON.stringify({ mode: "fold0_smoke" }),
          });
          state.notice = "Research run queued";
          renderProject();
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    const ens = document.getElementById("ensemble-run");
    if (ens) {
      ens.onclick = async () => {
        const raw = (document.getElementById("ensemble-oofs").value || "").trim();
        const oof_ids = raw ? raw.split(/[\s,]+/).filter(Boolean) : [];
        try {
          state.ensembleLast = await api("/v1/projects/" + pid() + "/ensemble", {
            method: "POST",
            body: JSON.stringify({ oof_ids, mode: "auto" }),
          });
          state.notice = "Ensemble " + (state.ensembleLast.status || "done");
          renderProject();
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    document.querySelectorAll(".lever-close").forEach((el) => {
      el.onclick = async () => {
        try {
          await api("/v1/projects/" + pid() + "/levers/" + el.getAttribute("data-id") + "/close", {
            method: "POST",
            body: JSON.stringify({ verdict: "kill" }),
          });
          await rerenderMode(true);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    });
    const labOpen = document.getElementById("lab-open-lever");
    if (labOpen) {
      labOpen.onclick = () => {
        state.mode = "BRAIN";
        setRoute("studio/" + pid() + "/brain");
      };
    }
    const apStart = document.getElementById("ap-start");
    if (apStart) {
      apStart.onclick = async () => {
        try {
          state.autopilot = await api("/v1/projects/" + pid() + "/autopilot/start", {
            method: "POST",
            body: JSON.stringify({ hours: 1, max_probes: 8, max_gpu_hours: 1, baseline_cv: 0 }),
          });
          state.notice = "Night shift " + (state.autopilot.status || "started");
          await rerenderMode(false);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    ["pause", "resume", "halt"].forEach((action) => {
      const el = document.getElementById("ap-" + action);
      if (!el) return;
      el.onclick = async () => {
        try {
          const path =
            action === "halt"
              ? "/autopilot/halt"
              : "/autopilot/" + action;
          state.autopilot = await api("/v1/projects/" + pid() + path, {
            method: "POST",
            body: action === "halt" ? JSON.stringify({ reason: "operator" }) : "{}",
          });
          await rerenderMode(false);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    });
    const digest = document.getElementById("ap-digest");
    if (digest) {
      digest.onclick = async () => {
        try {
          state.nightDigest = await api("/v1/projects/" + pid() + "/autopilot/digest");
          renderProject();
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
  }

  function bindKaggleActions() {
    const sync = document.getElementById("kaggle-sync");
    if (sync) {
      sync.onclick = async () => {
        try {
          await api("/v1/projects/" + pid() + "/kaggle/refresh", {
            method: "POST",
            body: JSON.stringify({ live: true }),
          });
          state.intelFor = null;
          state.notice = "Kaggle intel refreshed";
          await rerenderMode(false);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    const imp = document.getElementById("kaggle-import");
    if (imp) {
      imp.onclick = async () => {
        try {
          const out = await api("/v1/projects/" + pid() + "/kaggle/import-data", {
            method: "POST",
            body: JSON.stringify({ download: true }),
          });
          state.intelFor = null;
          const n = ((out.inventory || {}).files || []).length;
          state.notice = "Imported " + n + " file(s) from Kaggle";
          await rerenderMode(false);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    const diff = document.getElementById("kaggle-diff");
    if (diff) {
      diff.onclick = async () => {
        try {
          const out = await api("/v1/projects/" + pid() + "/kaggle/diff", {
            method: "POST",
            body: JSON.stringify({ left: [0.1, 0.2, 0.3], right: [0.1, 0.25, 0.3] }),
          });
          state.notice = "Diff ok · " + JSON.stringify(out).slice(0, 80);
          renderProject();
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    const pack = document.getElementById("kaggle-package");
    if (pack) {
      pack.onclick = async () => {
        try {
          const out = await api("/v1/projects/" + pid() + "/kaggle/package", {
            method: "POST",
            body: JSON.stringify({ files: [], final2: [] }),
          });
          state.notice = "Package " + JSON.stringify(out).slice(0, 80);
          renderProject();
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    const push = document.getElementById("kaggle-push");
    if (push) {
      push.onclick = async () => {
        try {
          const out = await api("/v1/projects/" + pid() + "/kaggle/push", {
            method: "POST",
            body: JSON.stringify({ credits: [] }),
          });
          state.notice = "Push " + JSON.stringify(out).slice(0, 80);
          renderProject();
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    const disc = document.getElementById("kaggle-discussion");
    if (disc) {
      disc.onclick = async () => {
        try {
          await api("/v1/projects/" + pid() + "/kaggle/discussions", {
            method: "POST",
            body: JSON.stringify({
              text: document.getElementById("disc-text").value || "",
              author: "studio",
            }),
          });
          state.notice = "Discussion ingested";
          renderProject();
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
  }

  function bindOpsActions() {
    const rp = document.getElementById("connect-runpod");
    if (rp) {
      rp.onclick = async () => {
        try {
          await api("/v1/orgs/current/cloud/connect/runpod", {
            method: "POST",
            body: JSON.stringify({ api_key: document.getElementById("runpod-key").value }),
          });
          state.accountsFor = null;
          state.notice = "RunPod connected";
          await rerenderMode(false);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    const aws = document.getElementById("connect-aws");
    if (aws) {
      aws.onclick = async () => {
        try {
          await api("/v1/orgs/current/cloud/connect/aws", {
            method: "POST",
            body: JSON.stringify({
              role_arn: document.getElementById("aws-role").value,
              region: "us-east-1",
            }),
          });
          state.accountsFor = null;
          state.notice = "AWS connected";
          await rerenderMode(false);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    const listGpus = document.getElementById("list-gpus");
    if (listGpus) {
      listGpus.onclick = async () => {
        try {
          state.gpus = await api("/v1/orgs/current/cloud/gpus?provider=runpod");
          renderProject();
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    document.querySelectorAll(".quote-gpu").forEach((el) => {
      el.onclick = async () => {
        const gpu_type = el.getAttribute("data-type");
        const cost = Number(el.getAttribute("data-cost") || 0);
        try {
          state.quote = await api(
            "/v1/orgs/current/cloud/quote?provider=runpod&gpu_type=" + encodeURIComponent(gpu_type)
          );
          if (!state.quote.within_entitlement) {
            state.notice = "Quote outside entitlement — not launching";
            renderProject();
            return;
          }
          await api("/v1/orgs/current/cloud/launch", {
            method: "POST",
            body: JSON.stringify({
              provider: "runpod",
              gpu_type,
              cost_estimate_micros_hr: cost || state.quote.cost_estimate_micros_hr,
              spot: true,
            }),
          });
          state.accountsFor = null;
          state.notice = "Launched " + gpu_type;
          await rerenderMode(false);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    });
    document.querySelectorAll(".runner-stop, .runner-term").forEach((el) => {
      el.onclick = async () => {
        const action = el.classList.contains("runner-stop") ? "stop" : "terminate";
        try {
          await api("/v1/orgs/current/runners/" + el.getAttribute("data-id") + "/" + action, {
            method: "POST",
            body: "{}",
          });
          state.accountsFor = null;
          await rerenderMode(false);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    });
    const gitPlan = document.getElementById("git-plan");
    if (gitPlan) {
      gitPlan.onclick = async () => {
        try {
          const installation_id = (document.getElementById("git-install").value || "").trim() || null;
          state.gitPlan = await api("/v1/projects/" + pid() + "/git/plan", {
            method: "POST",
            body: JSON.stringify({
              installation_id,
              pat_fallback: !installation_id,
              mission_id: "",
            }),
          });
          renderProject();
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
  }

  function bindTrustActions() {
    const share = document.getElementById("share");
    if (share) {
      share.onclick = async () => {
        try {
          const snap = await api("/v1/projects/" + pid() + "/share", {
            method: "POST",
            body: JSON.stringify({
              include_goals: true,
              include_lever_stats: true,
              include_dead_end_lessons: false,
            }),
          });
          state.notice = "Published " + snap.share_path;
          renderProject();
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    const harvest = document.getElementById("credits-harvest");
    if (harvest) {
      harvest.onclick = async () => {
        try {
          state.creditsBoard = await api("/v1/projects/" + pid() + "/credits/harvest", {
            method: "POST",
            body: JSON.stringify({
              source: document.getElementById("credit-source").value || "demo",
            }),
          });
          renderProject();
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    const verify = document.getElementById("credits-verify");
    if (verify) {
      verify.onclick = async () => {
        try {
          const credits = (state.creditsBoard && state.creditsBoard.credits) || [];
          state.creditsBoard = Object.assign({}, state.creditsBoard || {}, {
            verify: await api("/v1/projects/" + pid() + "/credits/verify", {
              method: "POST",
              body: JSON.stringify({ credits, gate: "kaggle_submit" }),
            }),
          });
          state.notice = "Credits verified";
          renderProject();
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    const exp = document.getElementById("credits-export");
    if (exp) {
      exp.onclick = async () => {
        try {
          const credits = (state.creditsBoard && state.creditsBoard.credits) || [];
          const out = await api("/v1/projects/" + pid() + "/credits/export", {
            method: "POST",
            body: JSON.stringify({ credits, title: "campaign" }),
          });
          state.creditsBoard = Object.assign({}, state.creditsBoard || {}, { export: out });
          state.notice = "Credits exported";
          renderProject();
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
    const invite = document.getElementById("trust-invite");
    if (invite) {
      invite.onclick = async () => {
        try {
          await api("/v1/projects/" + pid() + "/invite", {
            method: "POST",
            body: JSON.stringify({
              email: document.getElementById("trust-invite-email").value.trim(),
              role: "member",
            }),
          });
          state.modeDataFor = null;
          state.notice = "Invited";
          await rerenderMode(false);
        } catch (e) {
          state.error = String(e.message || e);
          renderProject();
        }
      };
    }
  }

  function renderProject() {
    showChrome("studio");
    const project = currentProject();
    const dash = state.dashboard;
    const mode = state.mode || "BRAIN";
    let body = "";
    if (mode === "GOALS") body = goalsBody(project, dash);
    else if (mode === "DEAD_ENDS") body = deadEndsBody(project, dash);
    else if (mode === "SOURCES") body = sourcesBody(project);
    else if (mode === "ROADMAP") body = roadmapBody(project);
    else if (mode === "GIT") body = gitBody(project);
    else if (mode === "LAB") body = labBody(project, dash);
    else if (mode === "KAGGLE") body = kaggleBody(project);
    else if (mode === "OPS") body = opsBody(project);
    else if (mode === "TRUST") body = trustBody(project);
    else body = overviewBody(project, dash);
    const title = (project && (project.name || project.slug)) || "Project";
    app.innerHTML = shell(title, body, "");
    bindShell(() => {
      document.querySelectorAll("[data-mode]").forEach((el) => {
        el.onclick = () => {
          const next = el.getAttribute("data-mode");
          state.mode = next;
          state.notice = "";
          state.modeDataFor = null;
          setRoute("studio/" + state.projectId + "/" + modePath(next));
        };
      });
      if (mode === "BRAIN") bindBrainActions();
      if (mode === "GOALS") bindGoalsActions();
      if (mode === "DEAD_ENDS") bindDeadEndsActions();
      if (mode === "SOURCES") bindSourcesActions();
      if (mode === "ROADMAP") bindRoadmapActions();
      if (mode === "GIT") bindGitActions();
      if (mode === "LAB") bindLabActions();
      if (mode === "KAGGLE") bindKaggleActions();
      if (mode === "OPS") bindOpsActions();
      if (mode === "TRUST") bindTrustActions();
    });
  }

  function renderLab() {
    showChrome("studio");
    const night = state.route === "lab/night" || state.route.endsWith("/night");
    const flags = ((state.me || {}).org || {}).feature_flags || {};
    const board =
      (state.nightDigest && state.nightDigest.ascii_board) ||
      [
        "LAB / Night-Shift Autopilot (stub)",
        "flag night_shift=" + String(!!flags.night_shift),
        "live: radar + file-tree MCTS (ascii.rest) — Motion=Active while running",
        "morning: fps={0} digest board + human CTAs (never auto Kaggle)",
        "API: POST /v1/projects/{id}/autopilot/start|pause|resume  GET status|digest",
      ].join("\n");
    app.innerHTML = `
<pre>lab ${night ? "/ night" : ""}</pre>
<p class="status">Research · Levers · Ensemble · Night-Shift · press : for palette</p>
${renderPalette()}
<pre class="board">${board.replace(/</g, "&lt;")}</pre>
<button class="cta" id="night-digest">[ load morning digest ]</button>
<button class="linkish" id="back-studio">[ back to studio ]</button>
<div class="err" id="err">${state.error || ""}</div>
`;
    bindPalette();
    document.getElementById("back-studio").onclick = () => setRoute("studio");
    document.getElementById("night-digest").onclick = async () => {
      if (!state.projectId) {
        state.error = "no project — open studio first";
        render();
        return;
      }
      try {
        state.nightDigest = await api(
          "/v1/projects/" + state.projectId + "/autopilot/digest"
        );
        state.error = "";
        setRoute("lab/night");
      } catch (e) {
        state.error =
          String(e.message || e) +
          " · enable feature_flags.night_shift and start a session";
        render();
      }
    };
  }

  async function ensureAuthed() {
    if (!state.token) {
      setRoute("login");
      return false;
    }
    if (!state.me) {
      try {
        state.me = await api("/v1/me");
      } catch (_) {
        state.token = "";
        localStorage.removeItem("mymlfw_token");
        setRoute("login");
        return false;
      }
    }
    return true;
  }

  async function render() {
    if (state.route === "lab" || state.route.startsWith("lab/")) {
      if (!(await ensureAuthed())) return;
      if (!state.projectId) {
        try {
          await loadStudio();
        } catch (e) {
          state.error = String(e.message || e);
        }
      }
      renderLab();
      return;
    }
    if (state.route === "settings") {
      if (!(await ensureAuthed())) return;
      try {
        state.settings = await api("/v1/settings");
      } catch (e) {
        state.error = String(e.message || e);
        state.settings = state.me;
      }
      try {
        state.pats = await api("/v1/orgs/current/pats");
      } catch (e) {
        state.pats = [];
      }
      renderSettings();
      return;
    }
    if (state.route === "studio" || state.route.startsWith("studio/")) {
      if (!(await ensureAuthed())) return;
      if (!state.projects.length && state.route !== "studio/new") {
        try {
          await loadStudio();
        } catch (e) {
          state.error = String(e.message || e);
        }
      }
      const parts = state.route.split("/");
      const projectId = parts[1] || "";
      const mode = modeFromPath(parts[2] || "brain");
      if (!projectId) {
        state.projectId = null;
        renderHome();
        return;
      }
      if (projectId === "new") {
        state.projectId = null;
        renderWizard();
        return;
      }
      state.projectId = projectId;
      state.mode = STUDIO_MODES.includes(mode) ? mode : "BRAIN";
      if (state.mode === "KAGGLE") {
        const project = currentProject() || state.projects.find((p) => p.id === projectId);
        if (project && project.kind !== "kaggle") {
          state.mode = "BRAIN";
          setRoute("studio/" + projectId + "/brain");
          return;
        }
      }
      if (!state.boards[projectId]) {
        try {
          state.boards[projectId] = await api("/v1/projects/" + projectId + "/dashboard");
        } catch (e) {
          state.error = String(e.message || e);
        }
      }
      state.dashboard = state.boards[projectId] || null;
      await loadModeData(false);
      connectTrainStrip();
      renderProject();
      return;
    }
    renderLogin();
  }

  window.addEventListener("hashchange", () => {
    state.route = location.hash.replace(/^#/, "") || "login";
    render();
  });

  window.addEventListener("keydown", (ev) => {
    const tag = (ev.target && ev.target.tagName) || "";
    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "k") {
      ev.preventDefault();
      state.paletteOpen = true;
      render();
      return;
    }
    if (tag === "INPUT" || tag === "TEXTAREA") return;
    if (ev.key >= "1" && ev.key <= String(STUDIO_MODES.length) && state.token && state.projectId && state.route.startsWith("studio/")) {
      const next = STUDIO_MODES[Number(ev.key) - 1];
      const project = currentProject();
      if (!next) return;
      if (next === "KAGGLE" && project && project.kind !== "kaggle") return;
      state.mode = next;
      setRoute("studio/" + state.projectId + "/" + modePath(next));
      return;
    }
    if ((ev.key === "j" || ev.key === "k") && state.route === "studio") {
      const count = filteredProjects().length;
      state.row = Math.max(0, Math.min(count - 1, state.row + (ev.key === "j" ? 1 : -1)));
      renderHome();
      return;
    }
    if (ev.key === "Enter" && state.route === "studio" && filteredProjects()[state.row]) {
      const id = filteredProjects()[state.row].id;
      state.mode = "BRAIN";
      setRoute("studio/" + id + "/brain");
    }
    if (ev.key === ":" && !state.paletteOpen && state.route.startsWith("studio")) {
      const tag = (ev.target && ev.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      ev.preventDefault();
      state.paletteOpen = true;
      state.paletteQuery = "";
      render();
    }
    if (ev.key === "Escape" && state.paletteOpen) {
      state.paletteOpen = false;
      render();
    }
  });

  render();
})();
