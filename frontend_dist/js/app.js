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
  };

  const FILTER_SELECTS = {
    exams: { el: document.getElementById("exam"), label: "exam" },
    states: { el: document.getElementById("state"), label: "state" },
    authorities: { el: document.getElementById("authority"), label: "authority" },
    courses: { el: document.getElementById("course"), label: "course" },
    categories: { el: document.getElementById("category"), label: "category" },
    quotas: { el: document.getElementById("quota"), label: "quota" },
  };

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

  // ------------------------------------------------------- filter lists
  async function loadFilterOptions() {
    Object.values(FILTER_SELECTS).forEach(({ el }) => (el.disabled = true));

    const { options, failed } = await window.NeetApi.allFilterOptions();

    Object.entries(FILTER_SELECTS).forEach(([key, { el, label }]) => {
      const items = options[key] || [];
      items.forEach((item) => {
        const opt = document.createElement("option");
        opt.value = item.name;
        opt.textContent = item.name;
        el.appendChild(opt);
      });
      if (failed.includes(key)) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = `Couldn't load ${label} list`;
        opt.disabled = true;
        el.appendChild(opt);
        el.disabled = true;
      } else {
        el.disabled = false;
      }
    });

    return options;
  }

  // ------------------------------------------------------- advanced UI
  els.advancedToggle.addEventListener("click", () => {
    const isOpen = els.advancedToggle.getAttribute("aria-expanded") === "true";
    els.advancedToggle.setAttribute("aria-expanded", String(!isOpen));
    els.advancedFilters.hidden = isOpen;
    els.advancedToggle.firstChild.textContent = isOpen
      ? "More filters (exam, state, course, category, quota) "
      : "Hide extra filters ";
  });

  els.resetBtn.addEventListener("click", () => {
    els.form.reset();
    els.rankError.textContent = "";
    els.rank.classList.remove("invalid");
    els.resultsSection.innerHTML = "";
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

  els.rank.addEventListener("input", () => {
    if (els.rank.classList.contains("invalid")) validateRank();
  });

  // ------------------------------------------------------- submit
  els.form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const rank = validateRank();
    if (rank === null) {
      els.rank.focus();
      return;
    }

    const filters = {};
    Object.entries(FILTER_SELECTS).forEach(([key, { el }]) => {
      if (el.value) {
        // API expects singular filter keys (exam, state, authority, course, category, quota)
        const filterKey = key.endsWith("ies") ? key.slice(0, -3) + "y" : key.replace(/s$/, "");
        filters[filterKey] = el.value;
      }
    });

    setLoading(true);
    renderLoading();

    try {
      const result = await window.NeetApi.predict({ rank, filters });
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

  function renderResults(data) {
    const total = data.total_results ?? (data.results ? data.results.length : 0);

    if (!data.results || data.results.length === 0) {
      els.resultsSection.innerHTML = `
        <div class="state-box">
          <p>${escapeHtml(data.message || "No results matched that rank and those filters.")}</p>
          <p>Try widening a filter, or removing one, and predict again.</p>
        </div>`;
      return;
    }

    const cards = data.results.map(renderResultCard).join("");
    els.resultsSection.innerHTML = `
      <div class="results-summary">
        <h3 class="serif">Results</h3>
        <span class="count">${total.toLocaleString("en-IN")} of ${(data.total_matching_records ?? total).toLocaleString("en-IN")} matching record${data.total_matching_records === 1 ? "" : "s"}</span>
      </div>
      ${data.message ? `<p class="results-summary" style="margin-top:-8px;color:var(--muted);font-size:13px;">${escapeHtml(data.message)}</p>` : ""}
      <div class="result-grid">${cards}</div>`;
    els.resultsSection.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  /**
   * Renders one PredictionResult. Every field is optional except
   * institute/close_rank/year/round/chance/margin_percent, per the
   * backend's schema — only fields actually present are shown.
   */
  function renderResultCard(r) {
    const metaItems = [];
    const add = (label, value, opts = {}) => {
      if (value === null || value === undefined || value === "") return;
      metaItems.push(`<div><span class="k">${label}</span><span class="v">${opts.raw ? value : escapeHtml(String(value))}</span></div>`);
    };

    add("Category", r.category);
    add("Quota", r.quota);
    add("Seat type", r.seat_type);
    add("Year", r.year);
    add("Round", r.round);
    add("Opening rank", typeof r.open_rank === "number" ? r.open_rank.toLocaleString("en-IN") : null);
    add("Closing rank", typeof r.close_rank === "number" ? r.close_rank.toLocaleString("en-IN") : null);
    add("Margin", typeof r.margin_percent === "number" ? `${r.margin_percent.toFixed(1)}%` : null);
    add("Fee", typeof r.fee === "number" ? `₹${r.fee.toLocaleString("en-IN")}` : null);

    const placeParts = [r.state, r.authority].filter(Boolean).join(" · ");

    return `
      <article class="result-card">
        <div class="result-card-head">
          <div>
            <h4>${escapeHtml(r.institute || "Institute")}${r.course ? ` — ${escapeHtml(r.course)}` : ""}</h4>
            ${placeParts ? `<div class="place">${escapeHtml(placeParts)}</div>` : ""}
          </div>
          ${r.chance ? `<span class="chance-badge" data-chance="${escapeHtml(r.chance)}">${escapeHtml(r.chance)}</span>` : ""}
        </div>
        <div class="result-meta">${metaItems.join("")}</div>
      </article>`;
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // ==================================================== colleges browse
  const collegeEls = {
    search: document.getElementById("collegeSearch"),
    clear: document.getElementById("collegeClear"),
    stateGrid: document.getElementById("stateGrid"),
    results: document.getElementById("collegeResults"),
  };

  let selectedState = null; // string or null
  let collegeDebounceTimer = null;

  function renderStateGrid(states) {
    if (!states || !states.length) {
      collegeEls.stateGrid.innerHTML = `<p class="state-box-inline">Couldn't load the list of states.</p>`;
      return;
    }
    collegeEls.stateGrid.innerHTML = states
      .map(
        (s) => `<button type="button" class="state-chip" data-state="${escapeHtml(s.name)}" aria-pressed="false">${escapeHtml(s.name)}</button>`
      )
      .join("");

    collegeEls.stateGrid.querySelectorAll(".state-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const stateName = chip.dataset.state;
        const alreadySelected = selectedState === stateName;
        selectedState = alreadySelected ? null : stateName;

        collegeEls.stateGrid.querySelectorAll(".state-chip").forEach((c) => c.setAttribute("aria-pressed", "false"));
        if (!alreadySelected) chip.setAttribute("aria-pressed", "true");

        runCollegeQuery();
      });
    });
  }

  collegeEls.search.addEventListener("input", () => {
    collegeEls.clear.hidden = collegeEls.search.value.trim() === "";
    clearTimeout(collegeDebounceTimer);
    collegeDebounceTimer = setTimeout(runCollegeQuery, 350);
  });

  collegeEls.clear.addEventListener("click", () => {
    collegeEls.search.value = "";
    collegeEls.clear.hidden = true;
    runCollegeQuery();
  });

  async function runCollegeQuery() {
    const term = collegeEls.search.value.trim();

    if (term.length === 1) {
      collegeEls.results.innerHTML = `<p class="state-box-inline">Keep typing — search needs at least 2 characters.</p>`;
      return;
    }

    const hasSearch = term.length >= 2;
    const hasState = Boolean(selectedState);

    if (!hasSearch && !hasState) {
      collegeEls.results.innerHTML = `<p class="state-box-inline">Pick a state above, or search by name, to see colleges.</p>`;
      return;
    }

    collegeEls.results.innerHTML = `<p class="state-box-inline">Loading…</p>`;

    try {
      if (hasState) {
        // A state is picked: pull REAL closing-rank data for every college
        // in it via /predict with rank=1 (the best possible rank), which
        // therefore matches every round on file for that state — this is
        // the same live endpoint the rank predictor above uses, just fed
        // a rank of 1 instead of the student's own rank. If a search term
        // is also typed, it narrows those real results client-side by
        // institute/course name — no separate name-search endpoint
        // supports doing both at once, so this keeps everything sourced
        // from one real API response rather than combining two calls.
        const data = await window.NeetApi.predict({ rank: 1, filters: { state: selectedState }, limit: 500 });
        let results = data.results || [];
        if (hasSearch) {
          const needle = term.toLowerCase();
          results = results.filter(
            (r) => (r.institute || "").toLowerCase().includes(needle) || (r.course || "").toLowerCase().includes(needle)
          );
        }
        renderStateTable(results, { hasSearch });
      } else {
        // No state picked, just a name search: the /colleges endpoint is
        // the only one that supports searching by name without a rank —
        // it returns names only, no closing-rank data.
        const list = await window.NeetApi.colleges({ search: term, limit: 100 });
        renderNameList(list);
      }
    } catch (err) {
      collegeEls.results.innerHTML = `
        <p class="state-box-inline error"><strong>Couldn't load that.</strong><br>${escapeHtml(err.message || "Please try again.")}</p>`;
    }
  }

  /** State selected: real closing-rank rows from /predict, one card per college+course+category. */
  function renderStateTable(results, { hasSearch }) {
    if (!results || results.length === 0) {
      const context = hasSearch ? ` matching "${escapeHtml(collegeEls.search.value.trim())}"` : "";
      collegeEls.results.innerHTML = `<p class="state-box-inline">No colleges found in ${escapeHtml(selectedState)}${context}.</p>`;
      return;
    }
    const cards = results.map(renderResultCard).join("");
    collegeEls.results.innerHTML = `
      <p class="college-results-summary">${results.length.toLocaleString("en-IN")} college/course record${results.length === 1 ? "" : "s"} in ${escapeHtml(selectedState)}, best closing rank first</p>
      <div class="result-grid">${cards}</div>`;
  }

  /** Name search only, no state picked: plain name list from /colleges (no rank data available here). */
  function renderNameList(list) {
    if (!list || list.length === 0) {
      collegeEls.results.innerHTML = `<p class="state-box-inline">No colleges found matching "${escapeHtml(collegeEls.search.value.trim())}".</p>`;
      return;
    }

    const items = list
      .map(
        (c) => `
        <div class="college-item">
          <span class="name">${escapeHtml(c.name)}</span>
          ${c.state ? `<span class="state">${escapeHtml(c.state)}</span>` : ""}
        </div>`
      )
      .join("");

    collegeEls.results.innerHTML = `
      <p class="college-results-summary">${list.length.toLocaleString("en-IN")} college${list.length === 1 ? "" : "s"} found${list.length === 100 ? " (showing first 100 — narrow your search for more precise results)" : ""}</p>
      <div class="college-list">${items}</div>`;
  }

  // ------------------------------------------------------- boot
  checkHealth();
  loadFilterOptions().then((options) => {
    renderStateGrid(options.states || []);
  });
})();
