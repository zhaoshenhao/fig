export const mockSessions = {
  sessions: [
    {
      chat_id: "chat_abc123",
      workflow: "auto_film",
      title: "隔热膜咨询",
      tags: ["隔热膜", "威固"],
      turn_count: 3,
      total_duration_ms: 5432,
      prompt_tokens: 120,
      completion_tokens: 80,
      last_at: "2026-07-15T10:30:00Z",
      rating: "up",
    },
    {
      chat_id: "chat_def456",
      workflow: "default",
      title: "通用问答",
      tags: [],
      turn_count: 1,
      total_duration_ms: 1234,
      prompt_tokens: 50,
      completion_tokens: 30,
      last_at: "2026-07-15T09:15:00Z",
      rating: null,
    },
  ],
  total: 2,
};

export const mockSessionsEmpty = { sessions: [], total: 0 };

export const mockSessionTurns = (chat_id) => ({
  chat_id,
  turns: [
    {
      turn_id: 0,
      run_id: "run_001",
      workflow: "auto_film",
      node_name: "generate",
      tool_name: "llm",
      input_text: "隔热膜怎么选？",
      output_text: "选隔热膜要关注以下几点...",
      duration_ms: 2000,
      status: "ok",
      started_at: "2026-07-15T10:29:58Z",
    },
  ],
});

export const mockTurnNodes = (chat_id, turn_id) => ({
  chat_id,
  turn_id,
  run: { run_id: "run_001", status: "ok", duration_ms: 2000 },
  nodes: [
    {
      node_log_id: 1,
      node_name: "retrieve",
      tool_name: "rag_search",
      duration_ms: 500,
      status: "ok",
    },
    {
      node_log_id: 2,
      node_name: "generate",
      tool_name: "llm",
      duration_ms: 1500,
      status: "ok",
    },
  ],
  feedback: [{ rating: "up", comment: "很有帮助", correction: null }],
  rag: [],
});

export const mockFilterFacets = {
  workflows: ["auto_film", "default", "if_then_wf"],
  nodes: ["retrieve", "generate", "router_a", "greet"],
  tools: ["llm", "rag_search", "router", "mock_echo"],
};
