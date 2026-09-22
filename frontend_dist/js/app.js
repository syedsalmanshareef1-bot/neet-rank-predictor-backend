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
    gridView: document.getElementById("collegeGridView"),
    tableView: document.getElementById("collegeTableView"),
    search: document.getElementById("collegeSearch"),
    clear: document.getElementById("collegeClear"),
    stateGrid: document.getElementById("stateGrid"),
    searchResults: document.getElementById("collegeSearchResults"),
    backBtn: document.getElementById("backToStatesBtn"),
    stateTitle: document.getElementById("stateViewTitle"),
    stateSubtitle: document.getElementById("stateViewSubtitle"),
    filterInstitute: document.getElementById("filterInstitute"),
    filterQuota: document.getElementById("filterQuota"),
    filterCourse: document.getElementById("filterCourse"),
    filterCategory: document.getElementById("filterCategory"),
    filterAuthority: document.getElementById("filterAuthority"),
    filterYear: document.getElementById("filterYear"),
    filterRound: document.getElementById("filterRound"),
    activeFilterCount: document.getElementById("activeFilterCount"),
    clearFiltersBtn: document.getElementById("clearTableFiltersBtn"),
    stateResults: document.getElementById("collegeStateResults"),
  };

  let selectedState = null;
  let collegeDebounceTimer = null;
  let institutDebounceTimer = null;
  let currentStateResults = []; // full, unfiltered /predict results for the selected state

  const FILTER_FIELD_MAP = {
    filterQuota: "quota",
    filterCourse: "course",
    filterCategory: "category",
    filterAuthority: "authority",
    filterYear: "year",
    filterRound: "round",
  };
  const tableFilters = { institute: "", quota: "", course: "", category: "", authority: "", year: "", round: "" };

  // ---------------------------------------------------------- state grid
  function renderStateGrid(states) {
    if (!states || !states.length) {
      collegeEls.stateGrid.innerHTML = `<p class="state-box-inline">Couldn't load the list of states.</p>`;
      return;
    }
    collegeEls.stateGrid.innerHTML = states
      .map((s) => {
        const v = window.StateMaps ? window.StateMaps.stateVisual(s.name) : { grad: ["#0d7377", "#14213d"], mapEntry: null, landmark: null };
        const gradId = "sg-" + s.name.replace(/[^a-zA-Z0-9]/g, "");
        const mapSvg = v.mapEntry
          ? `<svg class="state-map-svg" viewBox="${v.mapEntry.vb}" preserveAspectRatio="xMidYMid meet">
               <defs><linearGradient id="${gradId}" x1="0" y1="0" x2="1" y2="1">
                 <stop offset="0" stop-color="#fff" stop-opacity="0.96"/><stop offset="1" stop-color="#fff" stop-opacity="0.72"/>
               </linearGradient></defs>
               <path d="${v.mapEntry.d}" fill="url(#${gradId})"/>
             </svg>`
          : "";
        const badge = v.landmark ? `<div class="landmark-badge"><svg viewBox="0 0 24 24" fill="#fff">${v.landmark}</svg></div>` : "";
        return `
          <button type="button" class="state-card" data-state="${escapeHtml(s.name)}">
            <div class="state-card-banner" style="background:linear-gradient(135deg, ${v.grad[0]}, ${v.grad[1]});">
              ${mapSvg}${badge}
            </div>
            <div class="state-card-body">
              <div class="state-card-name">${escapeHtml(s.name)}</div>
            </div>
          </button>`;
      })
      .join("");

    collegeEls.stateGrid.querySelectorAll(".state-card").forEach((card) => {
      card.addEventListener("click", () => openState(card.dataset.state));
    });
  }

  // --------------------------------------------- top-level name search
  // (no state picked yet — /colleges is the only endpoint that supports
  // searching by name without a rank; it returns names only, no rank data)
  collegeEls.search.addEventListener("input", () => {
    collegeEls.clear.hidden = collegeEls.search.value.trim() === "";
    clearTimeout(collegeDebounceTimer);
    collegeDebounceTimer = setTimeout(runNameSearch, 350);
  });
  collegeEls.clear.addEventListener("click", () => {
    collegeEls.search.value = "";
    collegeEls.clear.hidden = true;
    runNameSearch();
  });

  async function runNameSearch() {
    const term = collegeEls.search.value.trim();
    if (!term) {
      collegeEls.searchResults.innerHTML = `<p class="state-box-inline">Pick a state above, or search by name, to see colleges.</p>`;
      return;
    }
    if (term.length === 1) {
      collegeEls.searchResults.innerHTML = `<p class="state-box-inline">Keep typing — search needs at least 2 characters.</p>`;
      return;
    }
    collegeEls.searchResults.innerHTML = `<p class="state-box-inline">Loading…</p>`;
    try {
      const list = await window.NeetApi.colleges({ search: term, limit: 100 });
      renderNameList(list);
    } catch (err) {
      collegeEls.searchResults.innerHTML = `
        <p class="state-box-inline error"><strong>Couldn't load that.</strong><br>${escapeHtml(err.message || "Please try again.")}</p>`;
    }
  }

  function renderNameList(list) {
    if (!list || list.length === 0) {
      collegeEls.searchResults.innerHTML = `<p class="state-box-inline">No colleges found matching "${escapeHtml(collegeEls.search.value.trim())}".</p>`;
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
    collegeEls.searchResults.innerHTML = `
      <p class="college-results-summary">${list.length.toLocaleString("en-IN")} college${list.length === 1 ? "" : "s"} found${list.length === 100 ? " (showing first 100 — pick a state, or narrow your search, for more precise results)" : ""}</p>
      <div class="college-list">${items}</div>`;
  }

  // ----------------------------------------------------- state -> table
  collegeEls.backBtn.addEventListener("click", showGrid);

  function showGrid() {
    collegeEls.tableView.hidden = true;
    collegeEls.gridView.hidden = false;
    selectedState = null;
  }

  async function openState(stateName) {
    selectedState = stateName;
    collegeEls.gridView.hidden = true;
    collegeEls.tableView.hidden = false;
    collegeEls.stateTitle.textContent = stateName;
    collegeEls.stateSubtitle.textContent = "Loading…";
    collegeEls.stateResults.innerHTML = `<p class="state-box-inline">Loading…</p>`;
    Object.keys(tableFilters).forEach((k) => (tableFilters[k] = ""));
    collegeEls.filterInstitute.value = "";

    try {
      // Real closing-rank data for every college in this state, via /predict
      // with rank=1 (the best possible rank) — the same live endpoint the
      // rank predictor above uses, just fed a rank of 1 instead of the
      // student's own rank, so it matches every round on file for the state.
      const data = await window.NeetApi.predict({ rank: 1, filters: { state: stateName }, limit: 500 });
      currentStateResults = data.results || [];
      const courseCount = new Set(currentStateResults.map((r) => r.course).filter(Boolean)).size;
      collegeEls.stateSubtitle.textContent =
        `${currentStateResults.length.toLocaleString("en-IN")} record(s) across ${courseCount.toLocaleString("en-IN")} course(s)`;
      renderFilterPanel(currentStateResults);
      applyFiltersAndRender();
    } catch (err) {
      collegeEls.stateSubtitle.textContent = "";
      collegeEls.stateResults.innerHTML = `
        <p class="state-box-inline error"><strong>Couldn't load colleges for ${escapeHtml(stateName)}.</strong><br>${escapeHtml(err.message || "Please try again.")}</p>`;
    }
  }

  /** Builds Quota/Course/Category/Authority/Year/Round dropdowns from the real fetched results — options are real values only, never invented. Note: the backend's prediction results don't include an "exam" field, so no Exam filter is offered here (unlike the rank predictor above, which does accept it as an input filter). */
  function renderFilterPanel(results) {
    const distinct = (key) => [...new Set(results.map((r) => r[key]).filter((v) => v !== null && v !== undefined && v !== ""))].sort();

    fillSelect(collegeEls.filterQuota, distinct("quota"));
    fillSelect(collegeEls.filterCourse, distinct("course"));
    fillSelect(collegeEls.filterCategory, distinct("category"));
    fillSelect(collegeEls.filterAuthority, distinct("authority"));
    fillSelect(collegeEls.filterYear, distinct("year"));
    fillSelect(collegeEls.filterRound, distinct("round"));
  }

  function fillSelect(selectEl, values) {
    const placeholder = selectEl.options[0]; // keep "All X" first option
    selectEl.innerHTML = "";
    selectEl.appendChild(placeholder);
    values.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = String(v);
      opt.textContent = String(v);
      selectEl.appendChild(opt);
    });
    selectEl.value = "";
  }

  Object.keys(FILTER_FIELD_MAP).forEach((id) => {
    collegeEls[id] || (collegeEls[id] = document.getElementById(id));
    document.getElementById(id).addEventListener("change", (e) => {
      tableFilters[FILTER_FIELD_MAP[id]] = e.target.value;
      applyFiltersAndRender();
    });
  });

  collegeEls.filterInstitute.addEventListener("input", () => {
    clearTimeout(institutDebounceTimer);
    institutDebounceTimer = setTimeout(() => {
      tableFilters.institute = collegeEls.filterInstitute.value.trim();
      applyFiltersAndRender();
    }, 250);
  });

  collegeEls.clearFiltersBtn.addEventListener("click", () => {
    Object.keys(tableFilters).forEach((k) => (tableFilters[k] = ""));
    collegeEls.filterInstitute.value = "";
    [collegeEls.filterQuota, collegeEls.filterCourse, collegeEls.filterCategory, collegeEls.filterAuthority, collegeEls.filterYear, collegeEls.filterRound].forEach(
      (el) => (el.value = "")
    );
    applyFiltersAndRender();
  });

  function applyFiltersAndRender() {
    let results = currentStateResults;
    if (tableFilters.quota) results = results.filter((r) => r.quota === tableFilters.quota);
    if (tableFilters.course) results = results.filter((r) => r.course === tableFilters.course);
    if (tableFilters.category) results = results.filter((r) => r.category === tableFilters.category);
    if (tableFilters.authority) results = results.filter((r) => r.authority === tableFilters.authority);
    if (tableFilters.year) results = results.filter((r) => String(r.year) === tableFilters.year);
    if (tableFilters.round) results = results.filter((r) => r.round === tableFilters.round);
    if (tableFilters.institute && tableFilters.institute.length >= 1) {
      const needle = tableFilters.institute.toLowerCase();
      results = results.filter(
        (r) => (r.institute || "").toLowerCase().includes(needle) || (r.course || "").toLowerCase().includes(needle)
      );
    }

    const activeCount = Object.values(tableFilters).filter(Boolean).length;
    collegeEls.activeFilterCount.textContent = activeCount ? `${activeCount} filter${activeCount === 1 ? "" : "s"} active` : "";

    renderCollegeTable(results);
  }

  /** Real closing-rank rows from /predict, rendered as a data table. */
  function renderCollegeTable(results) {
    if (!results || results.length === 0) {
      collegeEls.stateResults.innerHTML = `<p class="state-box-inline">No colleges found in ${escapeHtml(selectedState)} matching these filters.</p>`;
      return;
    }

    const rows = results
      .map((r) => {
        const rank = typeof r.close_rank === "number" ? r.close_rank.toLocaleString("en-IN") : "—";
        const fee = typeof r.fee === "number" ? `₹${r.fee.toLocaleString("en-IN")}` : "—";
        return `
        <tr>
          <td class="institute-cell" data-label="Institute">
            ${escapeHtml(r.institute || "—")}
            ${r.course ? `<span class="course-line">${escapeHtml(r.course)}</span>` : ""}
          </td>
          <td data-label="Category">${escapeHtml(r.category || "—")}</td>
          <td data-label="Quota">${escapeHtml(r.quota || "—")}</td>
          <td data-label="Authority">${escapeHtml(r.authority || "—")}</td>
          <td data-label="Year">${r.year ?? "—"}</td>
          <td data-label="Round">${escapeHtml(r.round || "—")}</td>
          <td data-label="Fee">${fee}</td>
          <td data-label="Closing rank"><span class="rank-pill" data-chance="${escapeHtml(r.chance || "")}">${rank}</span></td>
        </tr>`;
      })
      .join("");

    collegeEls.stateResults.innerHTML = `
      <p class="college-results-summary">${results.length.toLocaleString("en-IN")} of ${currentStateResults.length.toLocaleString("en-IN")} record(s), best closing rank first</p>
      <div class="college-table-wrap">
        <table class="college-table">
          <thead><tr><th>Institute</th><th>Category</th><th>Quota</th><th>Authority</th><th>Year</th><th>Round</th><th>Fee</th><th>Closing rank</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  // ------------------------------------------------------- boot
  checkHealth();
  loadFilterOptions().then((options) => {
    renderStateGrid(options.states || []);
  });
})();
