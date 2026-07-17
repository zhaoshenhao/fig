export const mockHealth = { status: "ok", timestamp: Date.now() / 1000 };

export const mockStatus = {
  status: "ok",
  timestamp: Date.now() / 1000,
  components: {
    qdrant: { status: "ok", latency_ms: 2.3, detail: "3 collections" },
    llm: { status: "ok", latency_ms: 45.2, detail: "provider=openai model=deepseek-chat" },
    embedding: { status: "ok", latency_ms: 12.1, detail: "model=nomic-embed-text host=kf-embed:8100" },
    metrics_store: { status: "ok", latency_ms: 0.5, detail: "SQLite ok" },
  },
  process: {
    version: "0.2.0",
    python: "3.14",
    uptime_seconds: 86400,
    workflow_count: 3,
    workflows: ["auto_film", "default", "if_then_wf"],
  },
};
