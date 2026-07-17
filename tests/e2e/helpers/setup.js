import {
  mockWorkflows, mockWorkflowDetail, mockWorkflowRunReply,
  mockSessions, mockFilterFacets, mockSessionTurns, mockTurnNodes,
  mockCollections, mockCollectionInfo, mockBrowseResults, mockSearchResults, mockCollectionCount,
  mockUploadResponse, mockScanResponse,
  mockSummary, mockTimeseries, mockFeedback,
  mockHealth, mockStatus,
} from "../fixtures/index.js";

export function installMocks(page) {
  page.route("**/health", (route) => route.fulfill({ status: 200, json: mockHealth }));

  page.route("**/status", (route) => route.fulfill({ status: 200, json: mockStatus }));

  page.route("**/api/v1/health", (route) => route.fulfill({ status: 200, json: { status: "ok" } }));

  page.route("**/api/v1/workflows", (route) => {
    if (route.request().method() === "GET") {
      route.fulfill({ status: 200, json: { workflows: mockWorkflows } });
    } else route.fallback();
  });

  page.route("**/api/v1/workflows/*/run", (route) => {
    route.fulfill({
      status: 200,
      json: { chat_id: "chat_mock_001", turn_id: "turn_001", reply: "模拟工作流响应内容。" },
    });
  });

  page.route("**/api/v1/workflows/*", (route) => {
    const url = route.request().url();
    if (url.match(/\/workflows\/[^/]+$/)) {
      const wfName = url.split("/").pop();
      route.fulfill({ status: 200, json: mockWorkflowDetail(wfName) });
    } else route.fallback();
  });

  page.route("**/api/v1/sessions/filters", (route) => {
    route.fulfill({ status: 200, json: mockFilterFacets });
  });

  page.route("**/api/v1/sessions", (route) => {
    if (route.request().method() === "GET") {
      route.fulfill({ status: 200, json: mockSessions });
    } else route.fallback();
  });

  page.route("**/collections", (route) => {
    route.fulfill({ status: 200, json: { collections: mockCollections } });
  });

  page.route("**/collections/*/count", (route) => {
    const col = route.request().url().match(/\/collections\/([^/]+)\/count/)[1];
    route.fulfill({ status: 200, json: mockCollectionCount(col) });
  });

  page.route("**/collections/*/browse**", (route) => {
    route.fulfill({ status: 200, json: mockBrowseResults });
  });

  page.route("**/collections/*/search**", (route) => {
    const q = new URL(route.request().url()).searchParams.get("q") || "";
    route.fulfill({ status: 200, json: mockSearchResults(q) });
  });

  page.route("**/collections/*", (route) => {
    const url = route.request().url();
    const name = url.match(/\/collections\/([^/]+)$/)?.[1] || "unknown";
    if (route.request().method() === "GET") {
      route.fulfill({ status: 200, json: mockCollectionInfo(name) });
    } else route.fallback();
  });

  page.route("**/metrics/summary**", (route) => {
    route.fulfill({ status: 200, json: mockSummary });
  });

  page.route("**/metrics/timeseries**", (route) => {
    const wf = new URL(route.request().url()).searchParams.get("workflow") || "auto_film";
    route.fulfill({ status: 200, json: mockTimeseries(wf) });
  });

  page.route("**/metrics/feedback**", (route) => {
    route.fulfill({ status: 200, json: mockFeedback });
  });

  page.route("**/export/training.jsonl**", (route) => {
    route.fulfill({
      status: 200,
      contentType: "application/x-ndjson",
      body: '{"query":"test","reply":"ans","feedback_rating":"up"}\n',
    });
  });

  page.route("**/api/v1/usage**", (route) => {
    route.fulfill({
      status: 200,
      json: {
        total_runs: 500, total_sessions: 200,
        prompt_tokens: 10000, completion_tokens: 8000,
        total_tokens: 18000, error_rate: 0.02,
      },
    });
  });
}
