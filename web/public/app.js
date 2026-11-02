/* Thin monospace shell — ascii.rest lands behind Motion=Active State (see web/AGENTS.md).
 * Agents: npx skills add bas3line/ascii
 * Phase B: Demo Campaign, Overview progress formula, `:` palette stub.
 */
(function () {
  const API = window.MYMLFW_API || "";
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
    error: "",
    trainStrip: null,
    sse: null,
  };

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
    const res = await fetch(API + path, Object.assign({}, opts, { headers }));
    const text = await res.text();
    let body = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch (_) {
      body = { raw: text };
    }
    if (!res.ok) {
      const msg =
        (body && (body.message || body.detail || body.error_code)) || res.statusText;
      throw new Error(String(msg));
    }
    return body;
  }

  async function afterAuth(tok) {
    state.token = tok.access_token;
    localStorage.setItem("mymlfw_token", state.token);
    state.me = await api("/v1/me");
    try {
      await api("/v1/studio/ensure-demo", { method: "POST", body: "{}" });
    } catch (_) {
      /* demo seed best-effort */
    }
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
    const demo = state.projects.find((p) => p.is_demo) || state.projects[0];
    if (demo) {
      state.projectId = demo.id;
      state.dashboard = await api("/v1/projects/" + demo.id + "/dashboard");
    }
  }

  function progressMeter(pct) {
    const n = Math.max(0, Math.min(10, Math.round((pct || 0) * 10)));
    return "[" + "=".repeat(n) + "-".repeat(10 - n) + "] " + ((pct || 0) * 100).toFixed(1) + "%";
  }

  function renderPalette() {
    if (!state.paletteOpen) return "";
    const cmds = [
      { key: "brain", label: "1 brain — Overview" },
      { key: "goals", label: "2 goals" },
      { key: "lab", label: "3 lab" },
      { key: "share", label: "share — publish public snapshot" },
      { key: "studio", label: "studio — project list" },
    ].filter((c) => !state.paletteQuery || c.label.includes(state.paletteQuery.toLowerCase()));
    return `
<div class="palette" id="palette">
  <pre>: command palette (stub)</pre>
  <input id="palette-input" placeholder="type a command…" value="${state.paletteQuery.replace(/"/g, "&quot;")}" />
  <ul class="palette-list">
    ${cmds.map((c) => `<li data-cmd="${c.key}">${c.label}</li>`).join("")}
  </ul>
  <p class="status">Esc closes · Phase B stub</p>
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
            state.error = "shared " + snap.share_path;
          } catch (e) {
            state.error = String(e.message || e);
          }
        }
        render();
      };
    });
  }

  function renderLogin() {
    app.innerHTML = `
<pre>login</pre>
<p class="status">Compose-local email/password. After login → Demo Campaign studio.</p>
<label>email</label>
<input id="email" type="email" value="owner@localhost" />
<label>password</label>
<input id="password" type="password" value="devpassword" />
<div class="row">
  <button class="cta" id="do-login">[ login ]</button>
  <button class="linkish" id="do-register">[ register instead ]</button>
</div>
<div class="err" id="err"></div>
`;
    document.getElementById("do-login").onclick = async () => {
      try {
        await login(
          document.getElementById("email").value,
          document.getElementById("password").value
        );
      } catch (e) {
        document.getElementById("err").textContent = String(e.message || e);
      }
    };
    document.getElementById("do-register").onclick = async () => {
      try {
        await register(
          document.getElementById("email").value,
          document.getElementById("password").value,
          "Dev"
        );
      } catch (e) {
        document.getElementById("err").textContent = String(e.message || e);
      }
    };
  }

  function renderStudio() {
    const me = state.me || {};
    const user = me.user || {};
    const org = me.org || {};
    const dash = state.dashboard;
    const h = (dash && dash.header) || {};
    const goals = (dash && dash.goals) || {};
    const levers = (dash && dash.levers) || {};
    const missions = (dash && dash.missions) || {};
    const dead = (dash && dash.dead_ends) || {};
    const projects = state.projects || [];
    const badges = (levers.fold_badges || [])
      .map((b) => b.display)
      .join(" · ");

    app.innerHTML = `
<pre>studio / brain</pre>
<p class="status">org=${org.slug || "-"} user=${user.email || "-"} persona=${me.persona || "unset"} · press : for palette</p>
${renderPalette()}
<pre class="board">
projects
${projects.map((p) => `  ${p.is_demo ? "*" : " "} ${p.slug}  ${p.kind}  ${p.id}`).join("\n") || "  (none)"}

overview  progress ${progressMeter(h.progress_pct)}
  formula  0.5*goals_met + 0.3*lever_close + 0.2*mission_success
  ratios   G=${(h.goals_met_ratio ?? 0).toFixed(3)}  L=${(h.lever_close_rate ?? 0).toFixed(3)}  M=${(h.mission_success_rate ?? 0).toFixed(3)}
  goal     ${h.primary_goal_title || "-"}  thr=${h.primary_threshold ?? "-"}  [${h.primary_status || "OPEN"}]
  adv_auc  ${h.adv_auc ?? "-"}  ${h.adv_auc_label || "UNKNOWN"}
  folds    sha=${(h.folds_sha256 || "-").slice(0, 12)}…

goals     active=${goals.active || 0} met=${goals.met || 0} abandoned=${goals.abandoned || 0}
levers    open=${levers.open || 0} closed=${levers.closed || 0} kills=${levers.kills || 0} promotes=${levers.promotes || 0}
  badges  ${badges || "-"}
missions  q=${missions.queued || 0} run=${missions.running || 0} ok=${missions.succeeded || 0} fail=${missions.failed || 0}
dead_ends ${dead.count || 0}  ${(dead.top_variables || []).join(", ") || "-"}
train     ${state.trainStrip ? `mode=${state.trainStrip.mode} pct=${state.trainStrip.progress_pct} ${state.trainStrip.message || ""}` : "(sse kit strip idle — connect on studio load)"}
</pre>
<button class="cta" id="refresh">[ refresh ]</button>
<button class="linkish" id="share">[ share ]</button>
<button class="linkish" id="logout">[ logout ]</button>
<div class="persona">
  <label>DEV persona switcher</label>
  <select id="persona">
    <option value="owner">owner</option>
    <option value="member">member</option>
    <option value="viewer">viewer</option>
    <option value="agent">agent</option>
  </select>
  <button class="cta" id="apply-persona">[ switch ]</button>
</div>
<div class="err" id="err">${state.error || ""}</div>
`;
    if (me.persona) document.getElementById("persona").value = me.persona;
    bindPalette();
    document.getElementById("refresh").onclick = async () => {
      state.error = "";
      try {
        state.me = await api("/v1/me");
        await loadStudio();
        render();
      } catch (e) {
        document.getElementById("err").textContent = String(e.message || e);
      }
    };
    document.getElementById("share").onclick = async () => {
      if (!state.projectId) return;
      try {
        const snap = await api("/v1/projects/" + state.projectId + "/share", {
          method: "POST",
          body: JSON.stringify({
            include_goals: true,
            include_lever_stats: true,
            include_dead_end_lessons: false,
          }),
        });
        state.error = "shared " + snap.share_path;
        render();
      } catch (e) {
        document.getElementById("err").textContent = String(e.message || e);
      }
    };
    document.getElementById("logout").onclick = () => {
      state.token = "";
      state.me = null;
      state.dashboard = null;
      state.projects = [];
      localStorage.removeItem("mymlfw_token");
      setRoute("login");
    };
    document.getElementById("apply-persona").onclick = async () => {
      try {
        await switchPersona(document.getElementById("persona").value);
      } catch (e) {
        document.getElementById("err").textContent = String(e.message || e);
      }
    };
  }

  async function render() {
    if (state.route === "studio" || state.route.startsWith("studio/")) {
      if (!state.token) {
        setRoute("login");
        return;
      }
      if (!state.me) {
        try {
          state.me = await api("/v1/me");
        } catch (_) {
          state.token = "";
          localStorage.removeItem("mymlfw_token");
          setRoute("login");
          return;
        }
      }
      if (!state.dashboard) {
        try {
          await loadStudio();
        } catch (e) {
          state.error = String(e.message || e);
        }
      }
      connectTrainStrip();
      renderStudio();
      return;
    }
    renderLogin();
  }

  window.addEventListener("hashchange", () => {
    state.route = location.hash.replace(/^#/, "") || "login";
    render();
  });

  window.addEventListener("keydown", (ev) => {
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
