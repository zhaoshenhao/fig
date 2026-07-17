export const mockWorkflows = [
  { name: "auto_film", description: "汽车膜产品智能助手" },
  { name: "default", description: "默认通用工作流" },
  { name: "if_then_wf", description: "条件分支测试工作流" },
];

export const mockWorkflowDetail = (name) => ({
  name,
  description: `工作流 ${name}`,
  collections: ["default"],
  return_mode: "full",
  nodes: [
    { name: "retrieve", tool: "rag_search", next_type: "one", next: "generate" },
    { name: "generate", tool: "llm", next_type: "one", next: "" },
  ],
});

export const mockWorkflowRunReply = (chat_id = "chat_mock_001") => ({
  chat_id,
  turn_id: "turn_001",
  reply: "这是来自工作流的模拟响应。",
});

export const mockWorkflowRunStreamTokens = [
  "这是", "来自", "工作流", "的", "模拟", "响应", "。",
];
