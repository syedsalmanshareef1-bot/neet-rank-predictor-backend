/**
 * NEET Rank Predictor — UI logic.
 * Talks only to window.NeetApi (js/api.js). Renders only fields the
 * backend actually returned — see renderResultCard().
 */
(function () {
  document.getElementById("year").textContent = new Date().getFullYear();

  const els = {
    statusPill: document.getElementById("backendStatus"),
    statusText: document.getElementById("backendStatusText"),
    heroFacts: document.getElementById("heroFacts"),
    form: document.getElementById("predictorForm"),
    rank: document.getElementById("rank"),
    rankError: document.getElementById("rankError"),
    advancedToggle: document.getElementById("advancedToggle"),
    advancedFilters: document.getElementById("advancedFilters"),
    submitBtn: document.getElementById("submitBtn"),
    resetBtn: document.getElementById("resetBtn"),
    resultsSection: document.getElementById("resultsSection"),
    userPill: document.getElementById("userPill"),
    userPillName: document.getElementById("userPillName"),
    logoutBtn: document.getElementById("logoutBtn"),
  };

  els.logoutBtn.addEventListener("click", () => window.NeetAuth.logout());

  async function loadCurrentUser() {
    try {
      const me = await window.NeetApi.me();
      els.userPillName.textContent = me.username;
      els.userPill.hidden = false;
    } catch (err) {
      // A failed /auth/me (expired session) already triggers a redirect to
      // login inside api.js — nothing extra to do here.
    }
  }

  const form = {
    course: document.getElementById("course"),
    courseHint: document.getElementById("courseHint"),
    homeState: document.getElementById("homeState"),
    homeStateError: document.getElementById("homeStateError"),
    state: document.getElementById("state"),
    quota: document.getElementById("quota"),
    quotaHint: document.getElementById("quotaHint"),
    studentCategory: document.getElementById("studentCategory"),
    gender: document.getElementById("gender"),
    isPwd: document.getElementById("isPwd"),
    eligibilityNote: document.getElementById("eligibilityNote"),
    seatTypeList: document.getElementById("seatTypeList"),
  };

  const HOME_STATE_KEY = "neet_home_state";
  let OPTIONS = null;          // from GET /predict/options
  let lastResults = null;      // last successful /predict response
  let activeChance = "all";    // chance tab currently shown

  // -------------------------------------------------------------- health
  async function checkHealth() {
    try {
      const h = await window.NeetApi.health();
      const ok = h && h.status === "ok";
      els.statusPill.dataset.state = ok ? "ok" : "down";
      els.statusText.textContent = ok ? "Live database connected" : "Data source degraded";

      const facts = [];
      if (typeof h.total_cutoff_records === "number") {
        facts.push(`<span><strong>${h.total_cutoff_records.toLocaleString("en-IN")}</strong> cutoff records</span>`);
      }
      if (typeof h.total_round_results === "number") {
        facts.push(`<span><strong>${h.total_round_results.toLocaleString("en-IN")}</strong> round results</span>`);
      }
      els.heroFacts.innerHTML = facts.join("");
    } catch (err) {
      els.statusPill.dataset.state = "down";
      els.statusText.textContent = "Can't reach backend";
    }
  }

  // ------------------------------------------------------- form options
  function setOptions(select, values, keepFirst = true) {
    const current = select.value;
    const first = keepFirst && select.options[0] ? select.options[0].outerHTML : "";
    select.innerHTML = first + values.map((v) => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join("");
    if ([...select.options].some((o) => o.value === current)) select.value = current;
  }

  async function loadFormOptions() {
    [form.course, form.homeState, form.state].forEach((el) => (el.disabled = true));
    try {
      OPTIONS = await window.NeetApi.predictOptions();
    } catch (err) {
      form.courseHint.textContent = "Couldn't load options from the server — reload the page to try again.";
      return;
    }
    setOptions(form.homeState, OPTIONS.home_states);
    setOptions(form.state, OPTIONS.counselling_states);
    let savedHome = null;
    try { savedHome = localStorage.getItem(HOME_STATE_KEY); } catch (e) { /* storage unavailable */ }
    if (savedHome && OPTIONS.home_states.includes(savedHome)) form.homeState.value = savedHome;

    form.seatTypeList.innerHTML = OPTIONS.seat_types.map((t) => `
      <label class="check-row">
        <input type="checkbox" name="seatType" value="${escapeHtml(t.id)}" ${t.default ? "checked" : ""}>
        <span>${escapeHtml(t.label)}</span>
      </label>`).join("");

    [form.course, form.homeState, form.state].forEach((el) => (el.disabled = false));
    refreshCourses();
    refreshQuotas();
    updateEligibilityNote();
  }

  /** Course list follows the counselling state, so every course offered has data there. */
  function refreshCourses() {
    if (!OPTIONS) return;
    const st = form.state.value;
    const list = st ? (OPTIONS.courses_by_state[st] || []) : OPTIONS.courses;
    const before = form.course.value;
    setOptions(form.course, list);
    if (before && !list.includes(before)) {
      form.courseHint.textContent = `${before} has no data in ${st} — showing all courses.`;
    } else {
      form.courseHint.textContent = "";
    }
  }

  /**
   * Quota list follows home state + counselling state: only quotas this
   * student can actually take are offered, grouped by seat type.
   */
  function refreshQuotas() {
    if (!OPTIONS || !OPTIONS.quotas_by_state) return;
    const home = form.homeState.value;
    const target = form.state.value;
    const states = target ? [target] : Object.keys(OPTIONS.quotas_by_state);
    const byName = new Map();
    states.forEach((st) => {
      (OPTIONS.quotas_by_state[st] || []).forEach((q) => {
        if (home && st !== home && !q.all_india) return; // domicile-only seat in another state
        if (!byName.has(q.name)) byName.set(q.name, { ...q, states: new Set() });
        byName.get(q.name).states.add(st);
      });
    });

    const labels = {};
    (OPTIONS.seat_types || []).forEach((t) => (labels[t.id] = t.label));
    const groups = new Map();
    [...byName.values()]
      .sort((a, b) => a.name.localeCompare(b.name))
      .forEach((q) => {
        if (!groups.has(q.seat_type)) groups.set(q.seat_type, []);
        groups.get(q.seat_type).push(q);
      });

    const before = form.quota.value;
    const order = (OPTIONS.seat_types || []).map((t) => t.id);
    let html = '<option value="">All quotas I\'m eligible for</option>';
    order.filter((id) => groups.has(id)).forEach((id) => {
      html += `<optgroup label="${escapeHtml(labels[id] || id)}">`;
      groups.get(id).forEach((q) => {
        // Short codes like "MNG" / "NRI" don't say which state they belong to.
        const st = [...q.states];
        const needsState = !target && st.length === 1 && !q.name.toLowerCase().includes(st[0].toLowerCase().slice(0, 3));
        const text = needsState ? `${q.name} (${st[0]})` : q.name;
        html += `<option value="${escapeHtml(q.name)}">${escapeHtml(text)}</option>`;
      });
      html += "</optgroup>";
    });
    form.quota.innerHTML = html;

    if (before && byName.has(before)) {
      form.quota.value = before;
    } else if (before) {
      form.quotaHint.textContent = `"${before}" isn't available for you here — showing all quotas.`;
      return;
    }
    updateQuotaHint();
  }

  function updateQuotaHint() {
    form.quotaHint.textContent = form.quota.value
      ? "Only this quota is searched (seat-type options below are ignored)."
      : "";
  }

  function updateEligibilityNote() {
    const home = form.homeState.value;
    const target = form.state.value;
    const note = form.eligibilityNote;
    note.classList.remove("ok");
    if (!home) { note.hidden = true; return; }
    if (!target) {
      note.textContent = `Showing all ${home} seats you qualify for, plus seats in other states that are open to all-India candidates. Outside ${home}, you compete as General — category reservation only applies in your home state.`;
    } else if (target === home) {
      note.classList.add("ok");
      note.textContent = `${home} is your home state, so its domicile (state quota) seats and your category reservation both apply.`;
    } else {
      note.textContent = `As a ${home} candidate you can only take ${target} seats that are open to all-India candidates (mostly private / management seats), and you compete as General there. ${target} state-quota seats are for ${target} domicile candidates only.`;
    }
    note.hidden = false;
  }

  form.state.addEventListener("change", () => { refreshCourses(); refreshQuotas(); updateEligibilityNote(); });
  form.quota.addEventListener("change", updateQuotaHint);
  form.homeState.addEventListener("change", () => {
    try { localStorage.setItem(HOME_STATE_KEY, form.homeState.value); } catch (e) { /* ignore */ }
    form.homeStateError.textContent = "";
    form.homeState.classList.remove("invalid");
    refreshQuotas();
    updateEligibilityNote();
  });

  // ------------------------------------------------------- advanced UI
  els.advancedToggle.addEventListener("click", () => {
    const isOpen = els.advancedToggle.getAttribute("aria-expanded") === "true";
    els.advancedToggle.setAttribute("aria-expanded", String(!isOpen));
    els.advancedFilters.hidden = isOpen;
    els.advancedToggle.firstChild.textContent = isOpen ? "More options (seat types) " : "Hide seat types ";
  });

  els.resetBtn.addEventListener("click", () => {
    const home = form.homeState.value;
    els.form.reset();
    form.homeState.value = home; // keep the student's own state
    els.rankError.textContent = "";
    els.rank.classList.remove("invalid");
    els.resultsSection.innerHTML = "";
    lastResults = null;
    if (OPTIONS) {
      form.seatTypeList.querySelectorAll("input").forEach((cb) => {
        const t = OPTIONS.seat_types.find((x) => x.id === cb.value);
        cb.checked = !!(t && t.default);
      });
    }
    refreshCourses();
    refreshQuotas();
    updateEligibilityNote();
  });

  // ------------------------------------------------------- validation
  function validateRank() {
    const raw = els.rank.value.trim();
    if (!raw) {
      els.rankError.textContent = "Enter your NEET rank to continue.";
      els.rank.classList.add("invalid");
      return null;
    }
    const n = Number(raw);
    if (!Number.isInteger(n) || n <= 0) {
      els.rankError.textContent = "Rank must be a positive whole number.";
      els.rank.classList.add("invalid");
      return null;
    }
    els.rankError.textContent = "";
    els.rank.classList.remove("invalid");
    return n;
  }

  function validateHomeState() {
    if (!form.homeState.value) {
      form.homeStateError.textContent = "Select your home state — it decides which seats you can take.";
      form.homeState.classList.add("invalid");
      return false;
    }
    form.homeStateError.textContent = "";
    form.homeState.classList.remove("invalid");
    return true;
  }

  els.rank.addEventListener("input", () => {
    if (els.rank.classList.contains("invalid")) validateRank();
  });

  // ------------------------------------------------------- submit
  els.form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const rank = validateRank();
    const homeOk = validateHomeState();
    if (rank === null) { els.rank.focus(); return; }
    if (!homeOk) { form.homeState.focus(); return; }

    const seatTypes = [...form.seatTypeList.querySelectorAll("input:checked")].map((cb) => cb.value);
    const filters = {
      home_state: form.homeState.value,
      state: form.state.value,
      course: form.course.value,
      quota: form.quota.value,
      student_category: form.studentCategory.value,
      gender: form.gender.value,
      is_pwd: form.isPwd.checked,
      seat_types: seatTypes.length ? seatTypes : ["government", "private"],
    };

    setLoading(true);
    renderLoading();

    try {
      const result = await window.NeetApi.predict({ rank, filters, limit: 2000 });
      lastResults = result;
      activeChance = "all";
      renderResults(result);
    } catch (err) {
      renderError(err);
    } finally {
      setLoading(false);
    }
  });

  function setLoading(isLoading) {
    els.submitBtn.disabled = isLoading;
    els.submitBtn.innerHTML = isLoading
      ? '<span class="spinner" aria-hidden="true"></span>Checking…'
      : "Predict my chances";
  }

  // ------------------------------------------------------- rendering
  function renderLoading() {
    els.resultsSection.innerHTML = `
      <div class="state-box">
        <p>Checking your rank against the live database…</p>
      </div>`;
    els.resultsSection.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function renderError(err) {
    const messages = {
      network: "Couldn't reach the prediction server. Check your connection and try again.",
      timeout: "The server took too long to respond. Please try again.",
      validation: err.message || "Please check the rank you entered.",
      server: "The server ran into a problem on its end. Please try again shortly.",
      config: "The predictor isn't configured correctly. Please contact the site owner.",
    };
    const text = messages[err.kind] || err.message || "Something went wrong.";
    els.resultsSection.innerHTML = `
      <div class="state-box error">
        <p><strong>Couldn't complete that prediction.</strong><br>${escapeHtml(text)}</p>
        <button type="button" class="btn-secondary" id="retryBtn">Try again</button>
      </div>`;
    document.getElementById("retryBtn").addEventListener("click", () => {
      els.form.requestSubmit();
    });
  }

  const CHANCES = ["High Chance", "Moderate Chance", "Borderline"];

  function renderResults(data) {
    if (!data.results || data.results.length === 0) {
      els.resultsSection.innerHTML = `
        <div class="state-box">
          <p>${escapeHtml(data.message || "No results matched that rank and those filters.")}</p>
          <p class="results-empty-hint">Try a different course, choose "All states I'm eligible for", or include more seat types under More options.</p>
        </div>`;
      els.resultsSection.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }

    const summary = data.summary || {};
    const shown = activeChance === "all" ? data.results : data.results.filter((r) => r.chance === activeChance);
    const tab = (key, label, n) =>
      `<button type="button" class="chance-tab" data-chance-tab="${escapeHtml(key)}" aria-pressed="${activeChance === key}">${escapeHtml(label)} (${n.toLocaleString("en-IN")})</button>`;

    els.resultsSection.innerHTML = `
      <div class="results-summary">
        <h3 class="serif">${data.results.length.toLocaleString("en-IN")} college &amp; course option${data.results.length === 1 ? "" : "s"}</h3>
        <span class="count">rank ${Number(data.rank_checked).toLocaleString("en-IN")} · from ${(data.total_eligible_records || 0).toLocaleString("en-IN")} seat records you're eligible for</span>
      </div>
      <div class="chance-tabs" role="group" aria-label="Filter by chance">
        ${tab("all", "All", data.results.length)}
        ${CHANCES.map((c) => tab(c, c, summary[c] || 0)).join("")}
      </div>
      <div class="result-grid">${shown.map(renderResultCard).join("") || '<p class="results-empty-hint">No results in this group.</p>'}</div>`;

    els.resultsSection.querySelectorAll("[data-chance-tab]").forEach((b) =>
      b.addEventListener("click", () => {
        activeChance = b.dataset.chanceTab;
        renderResults(lastResults);
      })
    );
  }

  function renderResultCard(r) {
    const metaItems = [];
    const add = (label, value) => {
      if (value === null || value === undefined || value === "") return;
      metaItems.push(`<div><span class="k">${label}</span><span class="v">${escapeHtml(String(value))}</span></div>`);
    };

    add("Quota", r.quota);
    add("Seat type", r.seat_type);
    add("Category", r.category);
    add("Closing rank", typeof r.close_rank === "number" ? `${r.close_rank.toLocaleString("en-IN")} (${r.year} ${r.round})` : null);
    add("Margin", typeof r.margin_percent === "number" ? `${r.margin_percent.toFixed(1)}%` : null);
    add("Fee", typeof r.fee === "number" ? `₹${r.fee.toLocaleString("en-IN")}` : null);

    const home = form.homeState.value;
    const tags = [];
    if (r.state && r.state === home) tags.push('<span class="tag home">Home state</span>');
    else if (r.open_to_all_india) tags.push('<span class="tag all-india">Open to all-India candidates</span>');
    if (r.other_routes > 0) tags.push(`<span class="tag routes">+${r.other_routes} other quota/category route${r.other_routes > 1 ? "s" : ""}</span>`);

    const rounds = r.latest_year_rounds || {};
    const cleared = new Set(r.cleared_in || []);
    const roundNames = Object.keys(rounds);
    const strip = roundNames.length
      ? `<div class="round-strip">${escapeHtml(String(r.latest_year || ""))} closing ranks by round: ${roundNames.map((rn) => {
          const hit = cleared.has(`${r.latest_year} ${rn}`);
          return `${escapeHtml(rn)} <b class="${hit ? "hit" : ""}">${Number(rounds[rn]).toLocaleString("en-IN")}</b>`;
        }).join(" · ")}</div>`
      : "";

    const placeParts = [r.state, r.authority].filter(Boolean).join(" · ");

    return `
      <article class="result-card">
        <div class="result-card-head">
          <div>
            <h4>${escapeHtml(r.institute || "Institute")}${r.course ? ` — ${escapeHtml(r.course)}` : ""}</h4>
            ${placeParts ? `<div class="place">${escapeHtml(placeParts)}</div>` : ""}
            ${tags.join("")}
          </div>
          ${r.chance ? `<span class="chance-badge" data-chance="${escapeHtml(r.chance)}">${escapeHtml(r.chance)}</span>` : ""}
        </div>
        <div class="result-meta">${metaItems.join("")}</div>
        ${strip}
      </article>`;
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // ==================================================== nav scrolling
  // Only one in-page view exists here now (the predictor). "Predictor",
  // "How it works" and "Admission info" all scroll within it. "Colleges"
  // is a normal link to /college — left alone, not intercepted.
  const navLinks = document.querySelectorAll("a[data-view]");

  navLinks.forEach((a) => {
    a.setAttribute("aria-current", a.dataset.view === "predictorView" && a.getAttribute("href") === "#predictor" ? "page" : "false");
    a.addEventListener("click", (e) => {
      e.preventDefault();
      const scrollTargetId = a.getAttribute("href").replace("#", "");
      const target = document.getElementById(scrollTargetId);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
      else window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  // ------------------------------------------------------- boot
  checkHealth();
  loadCurrentUser();
  loadFormOptions();
})();
