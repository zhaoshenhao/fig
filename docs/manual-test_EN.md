[中文](manual-test_CN.md)

# KF Manual Test Plan v2 — Supplemental Tasks

> Created: 2026-07-07
> Scope: Features added/changed after `manual-test-plan.md`
> Environment: FastAPI (Windows `.venv`, 9000) + Vue SPA (mounted at `/`) + Qdrant + Ollama

This document covers only features **not included in the original `manual-test-plan.md`**:

- **Session search filtering** (`/sessions` query params, 500 bug fixed on 2026-07-07)
- **auto_film automotive film workflow** (new product line)
- **Vue SPA frontend** (replaces Streamlit GUI)

---

## Command Conventions

Follows `manual-test-plan.md`:

**PowerShell**:
```powershell
$WIN_IP = "localhost"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

Frontend access: `http://localhost:9000/` (production build mounted at FastAPI root path);
Dev mode: `npm run dev` (`src/gui/ui/`, port 5173, requires Vite proxy to 9000).

---

## Layer S: Session Search Filtering (Regression Focus)

> Prerequisite: Existing execution records from `/api/v1/workflows/*/run` | Goal: Verify all `/sessions` filter/sort/pagination params
> Background: Previously using `node`/`tool`/`input_text`/`output_text` **individually** returned 500 (SQL missing WHERE clause), now fixed.

### Preparation
Run a few different workflows to generate data:
```powershell
Invoke-RestMethod -Uri http://$WIN_IP:9000/api/v1/workflows/auto_film/run -Method Post -ContentType "application/json; charset=utf-8" -Body '{"query":"隔热膜多少钱"}'
Invoke-RestMethod -Uri http://$WIN_IP:9000/api/v1/workflows/default/run -Method Post -ContentType "application/json; charset=utf-8" -Body '{"query":"你好"}'
```

### Test Cases

| # | Test Point | PowerShell | Expected Result |
|---|--------|------------|----------|
| S.1 | List without filters | `Invoke-RestMethod -Uri "http://$WIN_IP:9000/sessions"` | 200, `{sessions:[...], total:N}` |
| S.2 | **node filter alone** | `Invoke-RestMethod -Uri "http://$WIN_IP:9000/sessions?node=intent_classify"` | 200 (**not 500**), only sessions with that node |
| S.3 | **tool filter alone** | `Invoke-RestMethod -Uri "http://$WIN_IP:9000/sessions?tool=rag_search"` | 200 (**not 500**) |
| S.4 | **input_text filter alone** | `Invoke-RestMethod -Uri "http://$WIN_IP:9000/sessions?input_text=膜"` | 200 (**not 500**), sessions with "膜" in input |
| S.5 | **output_text filter alone** | `Invoke-RestMethod -Uri "http://$WIN_IP:9000/sessions?output_text=隔热"` | 200 (**not 500**) |
| S.6 | workflow filter | `Invoke-RestMethod -Uri "http://$WIN_IP:9000/sessions?workflow=auto_film"` | Only auto_film sessions |
| S.7 | Combined filters | `Invoke-RestMethod -Uri "http://$WIN_IP:9000/sessions?workflow=auto_film&tool=rag_search"` | Matches both conditions |
| S.8 | Four text params combined | `.../sessions?node=a&tool=b&input_text=c&output_text=d` | 200, typically total=0, no errors |
| S.9 | Duration range | `.../sessions?duration_min=100&duration_max=99999` | Only sessions within duration range |
| S.10 | Time range | `.../sessions?time_from=2026-01-01 00:00:00` | Only sessions after that time |
| S.11 | Sort - duration desc | `.../sessions?sort_by=duration_ms&sort_dir=desc` | First row is longest duration session |
| S.12 | Sort - turn count asc | `.../sessions?sort_by=turn_count&sort_dir=asc` | First row is fewest turns session |
| S.13 | Pagination | `.../sessions?limit=1&offset=0` vs `offset=1` | Different chat_id across pages, same total |
| S.14 | No match | `.../sessions?node=不存在的节点xyz` | 200, `sessions:[]`, `total:0` |

---

## Layer AF: auto_film Automotive Film Workflow

> Prerequisite: `car_film` collection indexed | Goal: Verify LLM intent classify → exact router → RAG / rejection routing
> Flow: intent_classify(LLM) → intent_route(router exact) → search_kb(RAG) → generate_answer(LLM)；Branch: → non_product_reply(LLM)

| # | Test Point | PowerShell | Expected Result |
|---|--------|------------|----------|
| AF.1 | Product inquiry match | `Body '{"query":"太阳膜和隔热膜有什么区别"}'` → `/api/v1/workflows/auto_film/run` | Goes through search_kb→generate_answer, reply contains film product info |
| AF.2 | Greeting (counts as product-related) | `Body '{"query":"你好"}'` | Classified as product-related, friendly response guiding to product inquiry |
| AF.3 | PPF inquiry | `Body '{"query":"隐形车衣贵不贵"}'` | Matches product scope, normal answer |
| AF.4 | Non-product routing | `Body '{"query":"今天股票涨了吗"}'` | Goes through non_product_reply, polite rejection guiding back to product inquiry |
| AF.5 | Intent classify determinism | Same query sent 2 times | Consistent routing branch |
| AF.6 | Multi-turn context | Run AF.1 to get chat_id, follow up: `'{"query":"那价格呢","chat_id":"<id>"}'` | Reply references previous film product, turn_id increments |
| AF.7 | Streaming mode | `.../api/v1/workflows/auto_film/run?stream=true` | SSE token stream + done event |
| AF.8 | Execution trace | Run once → `/sessions?workflow=auto_film` to get chat_id → `/api/v1/sessions/<id>/turns/0` | Contains intent_classify / intent_route / search_kb / generate_answer nodes |

---

## Layer V: Vue SPA Frontend (Replaces Original Layer 5 Streamlit)

> Prerequisite: `npm run build` has generated `dist/`, FastAPI mounts `/` | Goal: Verify 5-page functionality
> Access: `http://localhost:9000/`

### V.1 Chat Page (ChatPage)

| # | Action | Expected Result |
|---|------|----------|
| V.1.1 | Select workflow auto_film, type "隔热膜价格" and send | User/assistant bubbles displayed with timestamps; default **non-streaming** |
| V.1.2 | Check "Streaming" checkbox in chat bar, then send message | Character-by-character streaming display (off by default, per-session toggle) |
| V.1.3 | Send 3 messages in a row | Message area scrolls independently, input box stays at bottom |
| V.1.4 | Click "Clear" | Confirmation dialog appears, session clears on confirm |
| V.1.5 | Export JSON / CSV / Excel | Downloads corresponding file **with feedback/comment/correction columns** (feedback submitted in this session) |
| V.1.6 | Send message with FastAPI stopped | Shows specific error message; works normally after restart |
| V.1.7 | Click 👍 under assistant message | Expands feedback form with comment field; button highlights after "Submit", toast "Thank you for feedback"; `feedback` table has new rating=up + comment |
| V.1.8 | Click 👎 under assistant message | Expands feedback form with comment input + correction textarea; records rating=down + comment + correction on submit |
| V.1.9 | Click 🔄 Regenerate on last assistant message | Appends new turn response, turn_id increments |
| V.1.10 | Expand "Session Info", fill title + tags (comma-separated), click save | Toast "Session info saved"; `GET .../meta` shows title/tags |
| V.1.11 | Copy button 📋 (all assistant messages) | Content copied to clipboard |

### V.2 Knowledge Base Browser Page (KBBrowserPage)

| # | Action | Expected Result |
|---|------|----------|
| V.2.1 | Select collection `car_film` | Paginated document points displayed (id/source/text) |
| V.2.2 | Page navigation | Offset changes, content switches |
| V.2.3 | Type "隔热" in search box | "隔热" highlighted in results (`<mark>`) |
| V.2.4 | Collection list load failure (stop Qdrant) | Should show error (**known defect**: currently silent failure, empty dropdown) |

> ⚠️ Note: Current "search" is actually client-side highlighting of browse results, **not semantic search** (known defect P1-1). Record actual behavior during testing.

### V.3 Workflow Status Page (WorkflowStatusPage)

| # | Action | Expected Result |
|---|------|----------|
| V.3.1 | Expand auto_film | dagre.js renders DAG topology, nodes arranged by layer |
| V.3.2 | Click a node | Pops up that node's YAML config |
| V.3.3 | View customer_service | 5 nodes, with if-then branch markers |
| V.3.4 | Edit YAML `enabled: false`, click "Hot Reload" | Workflow disappears from list; `/workflows` returns fewer items |
| V.3.4b | Change back to `enabled: true`, hot reload | Workflow restored; selector reappears |
| V.3.5 | Click "Refresh" (no cache clear) | Different from "Reload": only re-fetches currently registered list |
| V.3.6 | Send chat request during hot reload | Returns 503 "config reload in progress", recovers after 1 second |

### V.4 Run Metrics Page (MetricsPage)

| # | Action | Expected Result |
|---|------|----------|
| V.4.1 | Open "Search & Filter" collapsible panel | Workflow/node name/tool name are **dropdown menus** (values from `/api/v1/sessions/filters`); user rating is dropdown (All/None/Good/Bad); time/input/output/duration filters |
| V.4.1b | Select workflow dropdown + search | **Exact match**, only returns sessions for that workflow |
| V.4.1c | Select "Bad" in user rating dropdown | Only returns sessions with 👎 feedback; "None" returns sessions with no rating at all |
| V.4.1d | Title/Tags columns | Session table has new "Title/Tags" column showing session_meta; sessions with saved titles show title + tag chips |
| V.4.1e | Title search | Type title keyword in filter panel → only returns sessions with matching title (persisted, searchable after session expires) |
| V.4.2 | **Search with only "Node" filter** | Results return normally (regression from Layer S.2, frontend no longer shows "Search failed") |
| V.4.3 | Search with only "Output Text" | Returns normally (regression from S.5) |
| V.4.4 | Click column header to sort | Results toggle asc/desc by column |
| V.4.5 | Previous/Next page | Pagination works correctly |
| V.4.6 | Click session row | Modal shows DAG execution status (executed=green/unexecuted=gray) + input/output panels |
| V.4.7 | Click executed node | Shows node input/output/tool call details |
| V.4.8 | Download session CSV | Downloads `sessions.csv` |

### V.5 Document Management Page (DocManagementPage)

| # | Action | Expected Result |
|---|------|----------|
| V.5.1 | Select "New" mode, enter collection name, upload .md | Shows chunk count, ingestion succeeds |
| V.5.2 | Upload .pdf / .docx / .csv / .xlsx | Each format accepted |
| V.5.3 | Select "Rebuild" mode, choose existing collection | **Known defect**: new/rebuild both call same endpoint, no rebuild param (P1-2), record actual behavior |
| V.5.4 | Select multiple files for upload | **Known defect**: only shows last file result (P3), record actual behavior |
| V.5.5 | Set chunk_size / chunk_overlap | Parameters take effect, chunk count changes accordingly |

### V.6 Global UI

| # | Action | Expected Result |
|---|------|----------|
| V.6.1 | Scroll page | Top bar title + tabs always sticky |
| V.6.2 | Enter API Key in sidebar | Status dot changes (green=connected/red=disconnected) |
| V.6.3 | Toggle dark/light theme | Theme switch works (**known defect**: FOUC flash on first load, P2) |
| V.6.4 | Mobile/narrow screen | Layout shrinks responsively |
| V.6.5 | After page refresh | **Known defect**: API Key not persisted, must re-enter (P2) |

---

## Feedback Template

```
Layer: [S / AF / V.x]
Test #: X.X
Result: [PASS / FAIL / Matches known defect]
Description: <short description>
```

---

## Layer W · 2026-07-07 Iteration Additions (Wave 1–5)

> Coverage: Security fixes, chat UX, system status page, semantic search, document rebuild, Metrics platformization.

### W1 Fixes & Security

| # | Test Point | Command / Action | Expected |
|---|--------|-------------|------|
| W1.1 | code_exec timeout | Run workflow through code tool executing `while True: pass` (timeout=1) | Returns `TimeoutError` after ~1s, no hang |
| W1.2 | Error sanitization | Trigger an internal 500 (e.g. mock failure) | Response body is `internal server error` + `request_id`, no stack trace/connection strings |
| W1.3 | Node error isolation | Make a node throw error, then send request | Request does not return 500 crash; `/sessions` shows that session's run status as error, node status as error |
| W1.4 | Non-destructive migration | Start with metrics.db using old schema | Old tables renamed `*_backup_*`, history preserved, new tables work |
| W1.5 | Ollama config | Start without `OLLAMA_BASE_URL` set | Uses production default `https://kaiwu.hix.ink/api/ollama/v1`; setting this env overrides to localhost |

### W2 Chat UX

| # | Test Point | Action | Expected |
|---|--------|------|------|
| W2.1 | Default non-streaming | Clear localStorage then open chat | "Streaming" checkbox is **unchecked** by default |
| W2.2 | Excel export | Send several messages → export conversation → Excel | Downloads `chat_history.xlsx`, opens in Excel, contains role/content/timestamp |
| W2.2b | CSV export | Same → CSV | UTF-8 BOM, Chinese characters not garbled |
| W2.3 | API error messages | Stop backend, send message | Message shows specific error (not "HTTP 400") |
| W2.4 | No theme flicker | Set dark theme → refresh page | No light→dark flicker (FOUC) |
| W2.4b | API Key persistence | Enter key → refresh | Key still present, no re-entry needed |
| W2.5 | Clear confirmation | Click "Clear" | Confirmation dialog appears, cancel does not clear |
| W2.6 | Markdown rendering | Have assistant reply with `**bold**`, `` `code` ``, code blocks | Formats and code highlighting render correctly |
| W2.7 | Keyboard shortcuts | Ctrl+Enter to send; press `/` when input not focused | Triggers send / focuses input respectively |

### W3 Core Features

| # | Test Point | Command / Action | Expected |
|---|--------|-------------|------|
| W3.1 | System status page | Sidebar → System Status | Shows Qdrant/Ollama LLM/Embedding/Metrics/(DB pool) cards + process info; overall status ok/degraded |
| W3.1b | /status endpoint | `Invoke-RestMethod http://$WIN_IP:9000/status` | Contains components + process(version/uptime/workflows) |
| W3.2 | Semantic search | KB Browser → select `car_film` → search "隔热膜" | Returns **semantic** results (score descending), matched terms highlighted |
| W3.2b | Search endpoint | `/collections/car_film/search?q=隔热膜` | 200, points contain text/score/source |
| W3.3 | Document rebuild | Doc Management → Rebuild mode → select existing collection, upload | Response `rebuilt=true`, collection cleared then rebuilt |
| W3.4 | Multi-file results | Upload multiple files at once (including one corrupt) | Summary shows success N/total + failure details |
| W3.5 | Esc to close modal | Chat record detail modal → press Esc | Modal closes |

### W5 Metrics Platformization

| # | Test Point | Command / Action | Expected |
|---|--------|-------------|------|
| W5.1 | Dashboard - Overview | Sidebar → Dashboard → Overview | First row global overview cards + per-workflow blocks sorted by usage frequency (workflow metric chips + node table + tool table, including P95/error rate) |
| W5.1b | Dashboard - Charts | Dashboard → Charts → select workflow + time range | Line charts: active sessions/request turns (per min)/avg latency/P95; 3 multi-line charts each for nodes and tools; custom time range takes effect |
| W5.2 | Summary endpoint | `/metrics/summary` | overview/by_workflow/by_tool/trend |
| W5.3 | Training export | Chat records page → Export training data / `/export/training.jsonl` | Downloads JSONL, each line contains `query/reply/feedback_rating/feedback_comment/feedback_correction`; `only_feedback=down` exports only negative samples |
| W5.3b | Feedback review | `GET /metrics/feedback?rating=down` | Returns negative feedback list with query/reply context |
| W5.8 | Dashboard rating metrics | Dashboard → Overview | Global + **each workflow** all include three items: rating rate / approval rate / feedback rate (with text) |
| W5.9 | Feedback review (removed tab) | Dashboard no longer has "Feedback" tab; feedback review uses `/metrics/feedback` API or chat records page rating filter |
| W5.10 | Approval rate chart | Dashboard → Charts → select workflow | Workflow area includes "Approval Rate (%)" line chart + "Feedback Volume (👍/👎)" multi-line chart |
| W5.11 | RAG retrieval details | Chat records → a turn with rag_search → click search_kb node | Status tab shows RAG retrieval details (N items/avg score) + each item preview (score/collection/source/content) |
| W5.12 | RAG quality overview | `GET /metrics/rag` | Returns overview(avg_score/min/max) + by_collection + by_source |
| W5.13 | Cost report | Dashboard → Overview | Global + each workflow includes "Cost (Est.)" card (tokens × `pricing.yaml` unit price) |
| W5.4 | Token stats | Run one LLM turn (provider returns usage), check `/api/v1/sessions/<id>` | Turn contains prompt_tokens/completion_tokens |
| W5.5 | Data retention | `POST /metrics/retention?days=1` | Returns deleted_runs; old records purged |
| W5.6 | Node/Tool metrics | `/metrics` | Contains `node_executions_total` / `node_duration_ms` / `tool_calls_total` / `workflow_runs_total` |
| W5.7 | Multi-engine | Set `KF_METRICS_ENGINE=mysql` + configure db pool (see `docs/metrics-db-setup_EN.md`) | Auto-creates tables on startup, read/write works; defaults to SQLite if not set |

---

## Layer X · External API Separation + New Features

> External API uses unified prefix `/api/v1/`; old `/workflows`, `/sessions` return 404.

| # | Test Point | Command / Action | Expected |
|---|--------|-------------|------|
| X.1 | Path migration | `GET /workflows` (old) vs `GET /api/v1/workflows` (new) | Old: 404; New: 200 returns list |
| X.2 | External health | `GET /api/v1/health` (no Key required) | `{"status":"ok",...}` |
| X.3 | Internal health still present | `GET /health` | 200, equivalent to X.2 |
| X.4 | Submit feedback 👍 | `POST /api/v1/sessions/{cid}/turns/0/feedback` body `{"rating":"up","comment":"好"}` | 200, returns feedback_id |
| X.5 | Submit feedback 👎+correction | body `{"rating":"down","correction":"正确答案"}` | 200 |
| X.6 | Invalid rating | body `{"rating":"maybe"}` | 422 |
| X.7 | Query feedback | `GET /api/v1/sessions/{cid}/turns/0/feedback` | Returns feedback array |
| X.8 | Regenerate | `POST /api/v1/workflows/auto_film/regenerate` body `{"chat_id":"{cid}"}` | 200, turn_id increments, reply is new answer |
| X.9 | Regenerate without session | chat_id does not exist | 404 |
| X.10 | Update session meta | `PATCH /api/v1/sessions/{cid}/meta` body `{"title":"VIP","tags":["vip"]}` | 200, returns title/tags |
| X.11 | Query session meta | `GET /api/v1/sessions/{cid}/meta` | Returns title/tags/workflow/turn_id |
| X.12 | Usage query | `GET /api/v1/usage` | Returns total_runs/total_sessions/total_tokens/error_rate |
| X.13 | Internal API unprefixed | `GET /collections`, `/status`, `/metrics/summary` | Still return normally at original paths |

### Feedback Template (same as above)

```
Layer: W
Test #: WX.X
Result: [PASS / FAIL / Matches known defect]
Description: <short description>
```
