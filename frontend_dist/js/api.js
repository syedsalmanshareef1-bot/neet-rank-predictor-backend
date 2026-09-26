/**
 * NEET Rank Predictor — API client
 * -----------------------------------------------------------------------
 * Every network call to the backend goes through this file. Nothing else
 * in the app should call `fetch()` directly against the API — this keeps
 * the base URL, error handling, timeouts and retry logic in one place.
 *
 * Talks to the real FastAPI backend documented at
 * https://predictor.eduoneinternational.com/docs — endpoints and payload
 * shapes below mirror app/routers/{health,meta,predict}.py and
 * app/schemas.py exactly. No response field is invented here; unknown or
 * missing fields are simply not shown by the UI layer (see app.js).
 */
(function () {
  const BASE_URL = (window.NEET_PREDICTOR_CONFIG && window.NEET_PREDICTOR_CONFIG.API_BASE_URL) || "";
  const DEFAULT_TIMEOUT_MS = 12000;

  /** Thrown for every failure mode so the UI can branch on `.kind`. */
  class ApiError extends Error {
    constructor(kind, message, detail) {
      super(message);
      this.kind = kind; // "network" | "timeout" | "validation" | "server" | "not_found"
      this.detail = detail;
    }
  }

  async function request(path, { method = "GET", body, timeoutMs = DEFAULT_TIMEOUT_MS, auth = true } = {}) {
    if (!BASE_URL) {
      throw new ApiError("config", "The API base URL is not configured. Check js/config.js.");
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    const headers = body ? { "Content-Type": "application/json" } : {};
    if (auth && window.NeetAuth) {
      const token = window.NeetAuth.getToken();
      if (token) headers["Authorization"] = "Bearer " + token;
    }

    let res;
    try {
      res = await fetch(BASE_URL + path, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
    } catch (err) {
      if (err.name === "AbortError") {
        throw new ApiError("timeout", "The server took too long to respond.");
      }
      throw new ApiError("network", "Could not reach the prediction server. Check your connection.");
    } finally {
      clearTimeout(timer);
    }

    let payload = null;
    const text = await res.text();
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = null;
      }
    }

    if (res.status === 401 && auth) {
      // Session missing or expired — send back to login rather than
      // showing a confusing error in place.
      if (window.NeetAuth) window.NeetAuth.logout();
      throw new ApiError("auth", "Your session has expired. Please log in again.", payload);
    }
    if (res.status === 404) {
      throw new ApiError("not_found", "That endpoint doesn't exist on the backend.", payload);
    }
    if (res.status === 422) {
      const msg = (payload && (payload.message || summarizeValidation(payload.detail))) || "Please check your input.";
      throw new ApiError("validation", msg, payload);
    }
    if (res.status >= 500) {
      throw new ApiError("server", (payload && payload.message) || "The server hit an internal error.", payload);
    }
    if (!res.ok) {
      throw new ApiError("server", (payload && payload.message) || `Request failed (${res.status}).`, payload);
    }

    return payload;
  }

  function summarizeValidation(detail) {
    if (!Array.isArray(detail) || !detail.length) return null;
    const first = detail[0];
    const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : "input";
    return `${field}: ${first.msg}`;
  }

  /** Retries a request once after a short delay — only for network/timeout failures. */
  async function withRetry(fn, retries = 1) {
    try {
      return await fn();
    } catch (err) {
      if (retries > 0 && (err.kind === "network" || err.kind === "timeout")) {
        await new Promise((r) => setTimeout(r, 800));
        return withRetry(fn, retries - 1);
      }
      throw err;
    }
  }

  const NeetApi = {
    ApiError,

    health() {
      return withRetry(() => request("/health"));
    },

    me() {
      return request("/auth/me");
    },

    // Reference-data lookups that populate the filter dropdowns.
    exams() {
      return withRetry(() => request("/exams"));
    },
    states() {
      return withRetry(() => request("/states"));
    },
    authorities() {
      return withRetry(() => request("/authorities"));
    },
    courses() {
      return withRetry(() => request("/courses"));
    },
    categories() {
      return withRetry(() => request("/categories"));
    },
    quotas() {
      return withRetry(() => request("/quotas"));
    },

    /** Fetches every filter list in parallel; a single failed list doesn't block the others. */
    async allFilterOptions() {
      const keys = ["exams", "states", "authorities", "courses", "categories", "quotas"];
      const settled = await Promise.allSettled(keys.map((k) => NeetApi[k]()));
      const out = {};
      const failed = [];
      settled.forEach((r, i) => {
        if (r.status === "fulfilled") {
          out[keys[i]] = r.value;
        } else {
          out[keys[i]] = [];
          failed.push(keys[i]);
        }
      });
      return { options: out, failed };
    },

    /** GET /predict/options — states, courses (per counselling state), categories, seat types. */
    predictOptions() {
      return withRetry(() => request("/predict/options"));
    },

    /**
     * POST /predict
     * @param {{rank: number, filters?: object, limit?: number}} payload
     */
    predict({ rank, filters = {}, limit = 500 }) {
      const cleanFilters = {};
      Object.entries(filters).forEach(([k, v]) => {
        if (v !== "" && v !== null && v !== undefined && v !== false) cleanFilters[k] = v;
      });
      return withRetry(() => request("/predict", { method: "POST", body: { rank, filters: cleanFilters, limit } }), 0);
    },

    /**
     * GET /colleges — optional state and search (min 2 chars, backend-enforced).
     * @param {{state?: string, search?: string, limit?: number}} params
     */
    colleges({ state, search, limit = 100 } = {}) {
      const qs = new URLSearchParams();
      if (state) qs.set("state", state);
      if (search && search.trim().length >= 2) qs.set("search", search.trim());
      if (limit) qs.set("limit", String(limit));
      const query = qs.toString();
      return withRetry(() => request(`/colleges${query ? `?${query}` : ""}`));
    },
  };

  window.NeetApi = NeetApi;
})();
