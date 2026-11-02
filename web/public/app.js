/* Thin monospace shell — ascii.rest lands behind Motion=Active State (see web/AGENTS.md).
 * Agents: npx skills add bas3line/ascii
 */
(function () {
  const API = window.MYMLFW_API || "";
  const app = document.getElementById("app");
  const state = {
    route: location.hash.replace(/^#/, "") || "login",
    token: localStorage.getItem("mymlfw_token") || "",
    me: null,
    error: "",
  };

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

  async function login(email, password) {
    const tok = await api("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    state.token = tok.access_token;
    localStorage.setItem("mymlfw_token", state.token);
    state.me = await api("/v1/me");
    setRoute("studio");
  }

  async function register(email, password, display_name) {
    const tok = await api("/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, display_name }),
    });
    state.token = tok.access_token;
    localStorage.setItem("mymlfw_token", state.token);
    state.me = await api("/v1/me");
    setRoute("studio");
  }

  async function switchPersona(persona) {
    state.me = await api("/v1/dev/persona", {
      method: "POST",
      body: JSON.stringify({ persona }),
    });
    render();
  }

  function renderLogin() {
    app.innerHTML = `
<pre>login</pre>
<p class="status">Compose-local email/password. GitHub OAuth stub available via API.</p>
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
      state.error = "";
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
    app.innerHTML = `
<pre>studio</pre>
<p class="status">org=${org.slug || "-"} user=${user.email || "-"} persona=${me.persona || "unset"}</p>
<p>Wave 1 shell — BRAIN/GOALS/LAB/KAGGLE/OPS/TRUST modes land in Phase B.</p>
<button class="cta" id="refresh">[ refresh me ]</button>
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
<div class="err" id="err"></div>
`;
    if (me.persona) document.getElementById("persona").value = me.persona;
    document.getElementById("refresh").onclick = async () => {
      try {
        state.me = await api("/v1/me");
        render();
      } catch (e) {
        document.getElementById("err").textContent = String(e.message || e);
      }
    };
    document.getElementById("logout").onclick = () => {
      state.token = "";
      state.me = null;
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
    if (state.route === "studio") {
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
      renderStudio();
      return;
    }
    renderLogin();
  }

  window.addEventListener("hashchange", () => {
    state.route = location.hash.replace(/^#/, "") || "login";
    render();
  });
  render();
})();
