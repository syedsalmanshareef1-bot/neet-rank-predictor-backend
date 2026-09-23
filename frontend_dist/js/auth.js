/**
 * NEET Rank Predictor — shared auth helper.
 * Token is stored in sessionStorage by default, or localStorage when the
 * person checked "Remember me" at login. requireAuth() is called at the
 * very top of every protected page, synchronously, so an unauthenticated
 * visitor is redirected before any protected content can flash on screen.
 */
(function () {
  const TOKEN_KEY = "neet_auth_token";

  function getToken() {
    return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY) || null;
  }

  function setToken(token, remember) {
    sessionStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(TOKEN_KEY);
    (remember ? localStorage : sessionStorage).setItem(TOKEN_KEY, token);
  }

  function clearToken() {
    sessionStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(TOKEN_KEY);
  }

  function requireAuth() {
    if (!getToken()) {
      window.location.replace("login.html");
    }
  }

  function logout() {
    clearToken();
    window.location.replace("login.html");
  }

  window.NeetAuth = { getToken, setToken, clearToken, requireAuth, logout };
})();
