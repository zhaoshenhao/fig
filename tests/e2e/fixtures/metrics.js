export const mockSummary = {
  overview: {
    total_runs: 1234,
    total_sessions: 567,
    error_rate: 0.02,
    avg_duration_ms: 2345,
    p50_duration_ms: 1800,
    p95_duration_ms: 8900,
    p99_duration_ms: 15000,
    prompt_tokens: 123456,
    completion_tokens: 98765,
    estimated_cost: 0.15,
    rating_rate: 0.35,
    satisfaction_rate: 0.88,
    feedback_rate: 0.12,
  },
  by_workflow: [
    {
      workflow: "auto_film",
      runs: 800,
      sessions: 400,
      error_rate: 0.01,
      avg_duration_ms: 2100,
      p95_duration_ms: 8000,
      prompt_tokens: 80000,
      completion_tokens: 60000,
      estimated_cost: 0.10,
      rating_rate: 0.4,
      feedback_rate: 0.15,
    },
  ],
  by_node: [
    { node_name: "retrieve", calls: 1200, avg_ms: 300, p95_ms: 800, error_rate: 0.01 },
    { node_name: "generate", calls: 1200, avg_ms: 2000, p95_ms: 8000, error_rate: 0.02 },
  ],
  by_tool: [
    { tool_name: "rag_search", calls: 1200, avg_ms: 300, p95_ms: 800, error_rate: 0.01 },
    { tool_name: "llm", calls: 1200, avg_ms: 2000, p95_ms: 8000, error_rate: 0.02 },
  ],
  trend: [
    { date: "2026-07-15", runs: 100, error_rate: 0.01 },
    { date: "2026-07-16", runs: 120, error_rate: 0.02 },
  ],
};

export const mockTimeseries = (workflow) => ({
  workflow,
  buckets: 24,
  workflow_series: {
    runs: Array.from({ length: 24 }, (_, i) => ({ t: i, v: Math.floor(Math.random() * 50) })),
    errors: Array.from({ length: 24 }, (_, i) => ({ t: i, v: 0 })),
    avg_duration: Array.from({ length: 24 }, (_, i) => ({ t: i, v: 2000 + Math.floor(Math.random() * 3000) })),
    tokens: Array.from({ length: 24 }, (_, i) => ({ t: i, v: 500 + Math.floor(Math.random() * 200) })),
  },
  nodes: [
    {
      name: "retrieve",
      series: {
        runs: Array.from({ length: 24 }, (_, i) => ({ t: i, v: Math.floor(Math.random() * 25) })),
        errors: Array.from({ length: 24 }, () => ({ t: 0, v: 0 })),
        avg_duration: Array.from({ length: 24 }, (_, i) => ({ t: i, v: 200 + Math.random() * 200 })),
      },
    },
  ],
  tools: [],
});

export const mockFeedback = {
  feedback: [
    { chat_id: "chat_001", turn_id: 0, rating: "up", comment: "专业回答", workflow: "auto_film" },
    { chat_id: "chat_002", turn_id: 0, rating: "down", comment: "不准确", workflow: "default" },
  ],
  count: 2,
};
