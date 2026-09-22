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
  // This section ports the exact table/round-pivot/heat-color logic from
  // frontend_integration/neet-rank-predictor-api-connected.html. The only
  // change is the data source: that file reads from a local, hand-imported
  // MASTER dataset; here, openState() fetches the SAME shape of data live
  // from the real backend via POST /predict (rank=1 matches every round on
  // file for that state), then groups it into the same
  // institute+quota+course+category "rows with nested rounds" structure
  // the original's renderTable() expects. Every number is real.
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
    resultsCount: document.getElementById("collegeResultsCount"),
    tableHead: document.getElementById("collegeTableHead"),
    tableBody: document.getElementById("collegeTableBody"),
  };

  let selectedState = null;
  let collegeDebounceTimer = null;
  let institutDebounceTimer = null;
  let currentStateRaw = []; // flat /predict results for the selected state, unfiltered

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
    collegeEls.resultsCount.textContent = "Loading…";
    collegeEls.tableHead.innerHTML = "";
    collegeEls.tableBody.innerHTML = "";
    collegeEls.filterInstitute.value = "";
    [collegeEls.filterQuota, collegeEls.filterCourse, collegeEls.filterCategory, collegeEls.filterAuthority, collegeEls.filterYear, collegeEls.filterRound].forEach(
      (el) => (el.value = "")
    );

    try {
      // Real closing-rank data for every college in this state, via /predict
      // with rank=1 (the best possible rank) — the same live endpoint the
      // rank predictor above uses, just fed a rank of 1 instead of the
      // student's own rank, so it matches every round on file for the state.
      const data = await window.NeetApi.predict({ rank: 1, filters: { state: stateName }, limit: 500 });
      currentStateRaw = data.results || [];
      const courseCount = new Set(currentStateRaw.map((r) => r.course).filter(Boolean)).size;
      collegeEls.stateSubtitle.textContent =
        `${currentStateRaw.length.toLocaleString("en-IN")} record(s) across ${courseCount.toLocaleString("en-IN")} course(s)`;

      fillSelect(collegeEls.filterQuota, distinct(currentStateRaw, "quota"));
      fillSelect(collegeEls.filterCourse, distinct(currentStateRaw, "course"));
      fillSelect(collegeEls.filterCategory, distinct(currentStateRaw, "category"));
      fillSelect(collegeEls.filterAuthority, distinct(currentStateRaw, "authority"));
      fillSelect(collegeEls.filterYear, distinct(currentStateRaw, "year"));
      fillSelect(collegeEls.filterRound, distinct(currentStateRaw, "round"));

      renderTable();
    } catch (err) {
      collegeEls.stateSubtitle.textContent = "";
      collegeEls.resultsCount.textContent = `Couldn't load colleges for ${stateName}: ${err.message || "please try again."}`;
    }
  }

  function distinct(rows, key) {
    return [...new Set(rows.map((r) => r[key]).filter((v) => v !== null && v !== undefined && v !== ""))].sort();
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

  const FILTER_FIELD_MAP = {
    filterQuota: "quota",
    filterCourse: "course",
    filterCategory: "category",
    filterAuthority: "authority",
    filterYear: "year",
    filterRound: "round",
  };
  Object.keys(FILTER_FIELD_MAP).forEach((id) => {
    document.getElementById(id).addEventListener("change", renderTable);
  });
  collegeEls.filterInstitute.addEventListener("input", () => {
    clearTimeout(institutDebounceTimer);
    institutDebounceTimer = setTimeout(renderTable, 250);
  });
  collegeEls.clearFiltersBtn.addEventListener("click", () => {
    Object.keys(FILTER_FIELD_MAP).forEach((id) => (document.getElementById(id).value = ""));
    collegeEls.filterInstitute.value = "";
    renderTable();
  });

  function roundKeyParts(k) {
    const [year, r] = k.split("-");
    return { year, round: r };
  }
  function sortRoundKeys(keys) {
    return keys.slice().sort((a, b) => {
      const A = roundKeyParts(a), B = roundKeyParts(b);
      if (A.year !== B.year) return A.year.localeCompare(B.year);
      if (A.round === "Final" && B.round === "Final") return 0;
      if (A.round === "Final") return 1;
      if (B.round === "Final") return -1;
      return (parseInt((A.round || "").replace(/\D/g, "")) || 0) - (parseInt((B.round || "").replace(/\D/g, "")) || 0);
    });
  }
  function roundLabel(key) {
    const p = roundKeyParts(key);
    return p.round === "Final" ? `${p.year} Final` : `${p.year} ${p.round}`;
  }
  function heatColor(value, min, max) {
    if (min === max) return { bg: "#FDE9C8", fg: "#8A4B0C" };
    const t = (value - min) / (max - min);
    if (t < 0.33) return { bg: "#FBE0DC", fg: "#A13D2F" };
    if (t < 0.66) return { bg: "#FDF0C8", fg: "#8A5A0C" };
    return { bg: "#DFF3E6", fg: "#1E7A4C" };
  }
  function naField(v) {
    return v === null || v === undefined || v === "" ? '<span class="na">Not Available</span>' : escapeHtml(String(v));
  }
  function formatFeeDisplay(fee) {
    if (fee === null || fee === undefined) return '<span class="rank-empty">-</span>';
    return "₹" + Number(fee).toLocaleString("en-IN") + "*";
  }

  /** Groups flat /predict rows into institute+quota+course+category "cards" with a nested per-round-key closing rank, exactly like the reference's local row model — just built from live API rows instead of imported ones. */
  function groupIntoRows(flatRows) {
    const map = new Map();
    flatRows.forEach((r) => {
      const key = [r.quota || "", r.institute || "", r.course || "", r.category || ""].join("|");
      if (!map.has(key)) {
        map.set(key, { quota: r.quota, institute: r.institute, course: r.course, category: r.category, fee: r.fee, rounds: {} });
      }
      const row = map.get(key);
      if (row.fee === null || row.fee === undefined) row.fee = r.fee;
      const roundKey = `${r.year}-${r.round}`;
      const existing = row.rounds[roundKey];
      if (!existing || (typeof r.close_rank === "number" && r.close_rank < existing.close)) {
        row.rounds[roundKey] = { open: r.open_rank ?? null, close: r.close_rank };
      }
    });
    return [...map.values()];
  }

  function renderTable() {
    if (!selectedState) return;

    const q = collegeEls.filterQuota.value;
    const c = collegeEls.filterCourse.value;
    const cat = collegeEls.filterCategory.value;
    const au = collegeEls.filterAuthority.value;
    const yr = collegeEls.filterYear.value;
    const rd = collegeEls.filterRound.value;
    const text = collegeEls.filterInstitute.value.trim().toLowerCase();

    let flat = currentStateRaw;
    if (q) flat = flat.filter((r) => r.quota === q);
    if (c) flat = flat.filter((r) => r.course === c);
    if (cat) flat = flat.filter((r) => r.category === cat);
    if (au) flat = flat.filter((r) => r.authority === au);
    if (yr) flat = flat.filter((r) => String(r.year) === yr);
    if (rd) flat = flat.filter((r) => r.round === rd);
    if (text) flat = flat.filter((r) => (r.institute || "").toLowerCase().includes(text) || (r.course || "").toLowerCase().includes(text));

    let rows = groupIntoRows(flat);

    const allRoundKeys = new Set();
    rows.forEach((r) => Object.keys(r.rounds).forEach((k) => allRoundKeys.add(k)));
    const roundKeysPresent = sortRoundKeys([...allRoundKeys]);

    const colStats = {};
    roundKeysPresent.forEach((k) => {
      const vals = rows.map((r) => (r.rounds[k] ? r.rounds[k].close : null)).filter((v) => v !== null);
      colStats[k] = { min: Math.min(...vals), max: Math.max(...vals) };
    });

    rows = rows.slice().sort((a, b) => {
      const av = Math.min(...Object.values(a.rounds).map((v) => v.close).filter((v) => v !== null), Infinity);
      const bv = Math.min(...Object.values(b.rounds).map((v) => v.close).filter((v) => v !== null), Infinity);
      return av - bv;
    });

    collegeEls.resultsCount.textContent = `${rows.length.toLocaleString("en-IN")} result(s)`;

    const activeCount = [q, c, cat, au, yr, rd, text].filter(Boolean).length;
    collegeEls.activeFilterCount.textContent = activeCount ? `${activeCount} filter${activeCount === 1 ? "" : "s"} active` : "";

    collegeEls.tableHead.innerHTML =
      '<tr><th class="sticky-col col-quota">Quota</th><th class="sticky-col col-institute">Institute</th><th>Course</th><th>Category</th><th>Fees</th>' +
      roundKeysPresent.map((k) => `<th class="round-col">${roundLabel(k)}</th>`).join("") +
      "</tr>";

    collegeEls.tableBody.innerHTML = rows
      .map((r) => {
        const cells = roundKeysPresent
          .map((k) => {
            const lbl = roundLabel(k);
            const v = r.rounds[k] ? r.rounds[k].close : null;
            if (v === null || v === undefined) return `<td class="round-cell rank-empty" data-label="${lbl}">-</td>`;
            const stat = colStats[k];
            const color = heatColor(v, stat.min, stat.max);
            return `<td class="round-cell" data-label="${lbl}"><span class="rank-pill" style="background:${color.bg};color:${color.fg};">${v.toLocaleString("en-IN")}</span></td>`;
          })
          .join("");
        const feeCell = `<td data-label="Fees">${formatFeeDisplay(r.fee)}</td>`;
        return (
          `<tr><td class="sticky-col col-quota" data-label="Quota"><span class="quota-pill">${naField(r.quota)}</span></td>` +
          `<td class="sticky-col col-institute" data-label="Institute" style="font-weight:600;">${escapeHtml(r.institute || "")}</td>` +
          `<td data-label="Course">${naField(r.course)}</td>` +
          `<td data-label="Category">${naField(r.category)}</td>` +
          feeCell +
          cells +
          `</tr>`
        );
      })
      .join("");
  }

  // ------------------------------------------------------- boot
  checkHealth();
  loadFilterOptions().then((options) => {
    renderStateGrid(options.states || []);
  });
})();
