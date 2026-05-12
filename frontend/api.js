// SimuVerse centralized API client
// Loaded as a plain script before any page scripts.
// Sets window.SimuVerseAPI = { API_BASE, WS_BASE, apiFetch, apiPost, apiDelete }

(function () {
  // Shared base URLs used by every frontend page.
  var API_BASE = (window.SIMUVERSE_API) || "http://localhost:8007/api";
  var WS_BASE = API_BASE.replace(/^http/, "ws");

  // Low-level fetch wrapper with timeout and consistent error parsing.
  async function apiFetch(path, options) {
    options = options || {};
    var url = API_BASE + path;
    var headers = Object.assign({}, options.headers || {});
    var method = (options.method || "GET").toUpperCase();

    if (method !== "GET" && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }

    var signal = options.signal || AbortSignal.timeout(15000);

    var response = await fetch(url, Object.assign({}, options, { headers: headers, signal: signal }));

    if (!response.ok) {
      var detail;
      try {
        var text = await response.text();
        if (text) {
          var body = JSON.parse(text);
          detail = body.detail || body.message || ("HTTP " + response.status);
        } else {
          detail = "HTTP " + response.status;
        }
      } catch (_) {
        detail = "HTTP " + response.status;
      }
      var err = new Error(detail);
      err.status = response.status;
      throw err;
    }

    return response.json();
  }

  // Small helpers for the request types the UI uses most.
  async function apiPost(path, body) {
    return apiFetch(path, {
      method: "POST",
      body: JSON.stringify(body || {}),
    });
  }

  async function apiDelete(path) {
    return apiFetch(path, { method: "DELETE" });
  }

  // Expose one shared client so page scripts do not duplicate fetch logic.
  window.SimuVerseAPI = {
    API_BASE: API_BASE,
    WS_BASE: WS_BASE,
    apiFetch: apiFetch,
    apiPost: apiPost,
    apiDelete: apiDelete,
  };
})();
