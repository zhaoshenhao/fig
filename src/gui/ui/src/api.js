import { useAppStore } from "./store.js";

const API_BASE = (typeof window !== "undefined" && window.KF_API_URL) || import.meta.env.VITE_API_URL || "";
const DEFAULT_TIMEOUT = 30000;

/** @returns {Record<string, string>} */
function authHeaders(extra = {}) {
  const store = useAppStore();
  const h = { ...extra };
  if (store.apiKey.value) h["X-API-Key"] = store.apiKey.value;
  return h;
}

/**
 * Extract a human-readable error message from a failed Response,
 * preferring the server's JSON `detail`/`error` fields.
 * @param {Response} r
 * @returns {Promise<Error>}
 */
async function toError(r) {
  let msg = `HTTP ${r.status}`;
  try {
    const ct = r.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      const body = await r.json();
      const detail = body.detail || body.error;
      if (detail) msg = typeof detail === "string" ? detail : JSON.stringify(detail);
    } else {
      const text = (await r.text()).trim();
      if (text) msg = text.slice(0, 300);
    }
  } catch { /* keep default msg */ }
  return new Error(msg);
}

/** fetch with a default timeout (unless a signal is already provided). */
function timedFetch(url, opts = {}, timeout = DEFAULT_TIMEOUT) {
  if (opts.signal) return fetch(url, opts);
  return fetch(url, { ...opts, signal: AbortSignal.timeout(timeout) });
}

/**
 * HTTP API client with automatic auth header injection.
 * @namespace
 */
export const api = {
  /**
   * @param {string} path
   * @param {Record<string, string|number>} [params]
   * @returns {Promise<any>}
   */
  async get(path, params = {}) {
    const qs = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();
    const url = `${API_BASE}${path}${qs ? "?" + qs : ""}`;
    const r = await timedFetch(url, { headers: authHeaders() });
    if (!r.ok) throw await toError(r);
    return r.json();
  },

  /**
   * @param {string} path
   * @param {any} body
   * @param {boolean} [useFormData=false]
   * @returns {Promise<any>}
   */
  async post(path, body, useFormData = false) {
    const opts = {
      method: "POST",
      headers: useFormData ? authHeaders() : authHeaders({ "Content-Type": "application/json" }),
      body: useFormData ? body : JSON.stringify(body),
    };
    // 文件上传等可能较慢，放宽超时
    const r = await timedFetch(`${API_BASE}${path}`, opts, useFormData ? 120000 : DEFAULT_TIMEOUT);
    if (!r.ok) throw await toError(r);
    return r.json();
  },

  /**
   * @param {string} path
   * @param {any} body
   * @returns {Promise<any>}
   */
  async patch(path, body) {
    const r = await timedFetch(`${API_BASE}${path}`, {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    });
    if (!r.ok) throw await toError(r);
    return r.json();
  },

  /**
   * GET expecting a binary file response (for downloads).
   * @param {string} path
   * @param {Record<string, string|number>} [params]
   * @returns {Promise<Blob>}
   */
  async getBlob(path, params = {}) {
    const qs = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();
    const url = `${API_BASE}${path}${qs ? "?" + qs : ""}`;
    const r = await timedFetch(url, { headers: authHeaders() });
    if (!r.ok) throw await toError(r);
    return r.blob();
  },

  /**
   * POST expecting a binary file response (for exports/downloads).
   * @param {string} path
   * @param {any} body
   * @returns {Promise<Blob>}
   */
  async postBlob(path, body) {
    const r = await timedFetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    });
    if (!r.ok) throw await toError(r);
    return r.blob();
  },

  /**
   * @param {string} path
   * @returns {Promise<any|null>}
   */
  async del(path) {
    const r = await timedFetch(`${API_BASE}${path}`, { method: "DELETE", headers: authHeaders() });
    if (!r.ok && r.status !== 204) throw await toError(r);
    return r.status === 204 ? null : r.json();
  },

  /**
   * SSE streaming request. Returns AbortController for cancellation.
   * @param {string} path
   * @param {any} body
   * @param {(token: string) => void} onToken
   * @param {(done: { chat_id: string, turn_id: number, reply: string }) => void} onDone
   * @param {(err: string) => void} onError
   * @returns {Promise<AbortController>}
   */
  async stream(path, body, onToken, onDone, onError) {
    const ctrl = new AbortController();
    try {
      const r = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      if (!r.ok) throw await toError(r);

      const reader = /** @type {ReadableStreamDefaultReader<Uint8Array>} */ (r.body.getReader());
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = /** @type {string} */ (lines.pop());

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            switch (evt.event) {
              case "token": onToken(evt.data); break;
              case "done": onDone(evt); break;
              case "error": onError(evt.data); break;
            }
          } catch { /* skip malformed lines */ }
        }
      }
    } catch (e) {
      if (e.name !== "AbortError") onError(e.message);
    }
    return ctrl;
  },

  /**
   * @returns {Promise<boolean>}
   */
  async health() {
    try {
      const r = await fetch(`${API_BASE}/health`, {
        headers: authHeaders(),
        signal: AbortSignal.timeout(3000),
      });
      return r.ok;
    } catch {
      return false;
    }
  },
};
