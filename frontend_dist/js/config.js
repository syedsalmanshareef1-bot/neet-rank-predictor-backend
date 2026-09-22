/**
 * NEET Rank Predictor — frontend configuration
 * -----------------------------------------------------------------------
 * This is the ONLY place the backend API URL is defined. Every other file
 * reads it from `window.NEET_PREDICTOR_CONFIG` — nothing else hardcodes it.
 *
 * This is a static (no-build-step) site, so there is no bundler to inject
 * a `.env` file at build time. This file *is* the equivalent of an env
 * file for a static deploy:
 *   - Edit API_BASE_URL below directly, OR
 *   - If your host supports it, generate this file from an environment
 *     variable during deploy (e.g. `envsubst < config.template.js >
 *     config.js`, or a Netlify/Vercel build command). See README.md
 *     ("Environment configuration") for exact recipes.
 *
 * Precedence: if `window.NEET_PREDICTOR_CONFIG` is injected by some other
 * script tag *before* this file loads (e.g. a small inline snippet the
 * host adds at deploy time), that value wins and this file is skipped.
 */
window.NEET_PREDICTOR_CONFIG = window.NEET_PREDICTOR_CONFIG || {
  // Base URL of the existing FastAPI backend, INCLUDING the /api/v1 prefix.
  // The backend is already live at this address — do not point this at
  // anything else without also updating CORS_ORIGINS on the backend.
  API_BASE_URL: "https://predictor.eduoneinternational.com/api/v1",
};
