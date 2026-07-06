import { store } from "./store.js";

const API_BASE = import.meta.env.VITE_API_URL || "";

function headers() {
  const h = { "Content-Type": "application/json" };
  if (store.apiKey) h["X-API-Key"] = store.apiKey;
  return h;
}

function formHeaders() {
  const h = {};
  if (store.apiKey) h["X-API-Key"] = store.apiKey;
  return h;
}

export const api = {
  async get(path, params = {}) {
    const qs = new URLSearchParams(params).toString();
    const url = `${API_BASE}${path}${qs ? "?" + qs : ""}`;
    const r = await fetch(url, { headers: headers() });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  },

  async post(path, body, useFormData = false) {
    const url = `${API_BASE}${path}`;
    const opts = {
      method: "POST",
      headers: useFormData ? formHeaders() : headers(),
      body: useFormData ? body : JSON.stringify(body),
    };
    const r = await fetch(url, opts);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  },

  async del(path) {
    const r = await fetch(`${API_BASE}${path}`, {
      method: "DELETE",
      headers: headers(),
    });
    if (!r.ok && r.status !== 204) throw new Error(`HTTP ${r.status}`);
    return r.status === 204 ? null : r.json();
  },

  async stream(path, body, onToken, onDone, onError) {
    const url = `${API_BASE}${path}`;
    const ctrl = new AbortController();
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: headers(),
        body: JSON.stringify(body),
        signal: ctrl.signal,
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop();
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const evt = JSON.parse(line.slice(6));
              if (evt.event === "token") onToken(evt.data);
              else if (evt.event === "done") onDone(evt);
              else if (evt.event === "error") onError(evt.data);
            } catch (_) {}
          }
        }
      }
    } catch (e) {
      if (e.name !== "AbortError") onError(e.message);
    }
    return ctrl;
  },

  async health() {
    try {
      const r = await fetch(`${API_BASE}/health`, {
        headers: headers(),
        signal: AbortSignal.timeout(3000),
      });
      return r.ok;
    } catch {
      return false;
    }
  },
};
