# KF 人工测试计划 v2 — 补充任务

> 创建时间: 2026-07-07
> 补充范围: `manual-test-plan.md` 之后新增/变更的功能
> 环境: FastAPI (Windows `.venv`, 9000) + Vue SPA (挂载于 `/`) + Qdrant + Ollama

本文件仅覆盖**原 `manual-test-plan.md` 未包含**的功能，包括：

- **会话搜索过滤**（`/sessions` 查询参数，2026-07-07 修复的 500 缺陷）
- **auto_film 汽车膜工作流**（新产品线）
- **Vue SPA 前端**（已替换 Streamlit GUI）

---

## 命令规范

沿用 `manual-test-plan.md`：

**PowerShell**:
```powershell
$WIN_IP = "localhost"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

前端访问: `http://localhost:9000/`（生产构建挂载于 FastAPI 根路径）；
开发模式: `npm run dev`（`src/gui/ui/`，端口 5173，需 Vite proxy 指向 9000）。

---

## Layer S: 会话搜索过滤（回归重点）

> 依赖: 已有若干 `/api/v1/workflows/*/run` 产生的执行记录 | 目标: 验证 `/sessions` 全部过滤/排序/分页参数
> 背景: 此前仅 `node`/`tool`/`input_text`/`output_text` **单独使用**时返回 500（SQL 缺 WHERE），现已修复。

### 准备
先跑几轮不同工作流产生数据：
```powershell
Invoke-RestMethod -Uri http://$WIN_IP:9000/api/v1/workflows/auto_film/run -Method Post -ContentType "application/json; charset=utf-8" -Body '{"query":"隔热膜多少钱"}'
Invoke-RestMethod -Uri http://$WIN_IP:9000/api/v1/workflows/default/run -Method Post -ContentType "application/json; charset=utf-8" -Body '{"query":"你好"}'
```

### 测试用例

| # | 测试点 | PowerShell | 预期结果 |
|---|--------|------------|----------|
| S.1 | 无过滤列出 | `Invoke-RestMethod -Uri "http://$WIN_IP:9000/sessions"` | 200，`{sessions:[...], total:N}` |
| S.2 | **node 单独过滤** | `Invoke-RestMethod -Uri "http://$WIN_IP:9000/sessions?node=intent_classify"` | 200（**非 500**），仅含该节点的会话 |
| S.3 | **tool 单独过滤** | `Invoke-RestMethod -Uri "http://$WIN_IP:9000/sessions?tool=rag_search"` | 200（**非 500**） |
| S.4 | **input_text 单独过滤** | `Invoke-RestMethod -Uri "http://$WIN_IP:9000/sessions?input_text=膜"` | 200（**非 500**），命中含"膜"输入的会话 |
| S.5 | **output_text 单独过滤** | `Invoke-RestMethod -Uri "http://$WIN_IP:9000/sessions?output_text=隔热"` | 200（**非 500**） |
| S.6 | workflow 过滤 | `Invoke-RestMethod -Uri "http://$WIN_IP:9000/sessions?workflow=auto_film"` | 仅 auto_film 会话 |
| S.7 | 组合过滤 | `Invoke-RestMethod -Uri "http://$WIN_IP:9000/sessions?workflow=auto_film&tool=rag_search"` | 同时满足两条件 |
| S.8 | 四项文本组合 | `.../sessions?node=a&tool=b&input_text=c&output_text=d` | 200，通常 total=0，无报错 |
| S.9 | 时长区间 | `.../sessions?duration_min=100&duration_max=99999` | 仅耗时在区间内的会话 |
| S.10 | 时间区间 | `.../sessions?time_from=2026-01-01 00:00:00` | 仅该时间后的会话 |
| S.11 | 排序-耗时降序 | `.../sessions?sort_by=duration_ms&sort_dir=desc` | 首行为耗时最大会话 |
| S.12 | 排序-轮次升序 | `.../sessions?sort_by=turn_count&sort_dir=asc` | 首行为轮次最少会话 |
| S.13 | 分页 | `.../sessions?limit=1&offset=0` 与 `offset=1` | 两页 chat_id 不同，total 一致 |
| S.14 | 无匹配 | `.../sessions?node=不存在的节点xyz` | 200，`sessions:[]`, `total:0` |

---

## Layer AF: auto_film 汽车膜工作流

> 依赖: `car_film` 集合已入库 | 目标: 验证 LLM 意图分类 → exact router → RAG / 拒答分流
> 流程: intent_classify(LLM) → intent_route(router exact) → search_kb(RAG) → generate_answer(LLM)；分流: → non_product_reply(LLM)

| # | 测试点 | PowerShell | 预期结果 |
|---|--------|------------|----------|
| AF.1 | 产品咨询命中 | `Body '{"query":"太阳膜和隔热膜有什么区别"}'` → `/api/v1/workflows/auto_film/run` | 走 search_kb→generate_answer，reply 含膜产品信息 |
| AF.2 | 打招呼（算产品相关） | `Body '{"query":"你好"}'` | 判定为产品相关，友好回应并引导咨询 |
| AF.3 | 隐形车衣咨询 | `Body '{"query":"隐形车衣贵不贵"}'` | 命中产品范围，正常回答 |
| AF.4 | 非产品问题分流 | `Body '{"query":"今天股票涨了吗"}'` | 走 non_product_reply，友好拒绝并引导回产品咨询 |
| AF.5 | 意图分类确定性 | 同一 query 连发 2 次 | 路由分支一致 |
| AF.6 | 多轮上下文 | 先 AF.1 拿 chat_id，续问 `'{"query":"那价格呢","chat_id":"<id>"}'` | reply 引用前文膜产品，turn_id 递增 |
| AF.7 | 流式模式 | `.../api/v1/workflows/auto_film/run?stream=true` | SSE token 流 + done 事件 |
| AF.8 | 执行 trace 记录 | 跑一轮后 `/sessions?workflow=auto_film` 拿 chat_id → `/api/v1/sessions/<id>/turns/0` | 含 intent_classify / intent_route / search_kb / generate_answer 节点 |

---

## Layer V: Vue SPA 前端（替代原 Layer 5 Streamlit）

> 依赖: `npm run build` 已生成 `dist/`，FastAPI 挂载 `/` | 目标: 验证 5 页面功能
> 访问: `http://localhost:9000/`

### V.1 聊天页 (ChatPage)

| # | 操作 | 预期结果 |
|---|------|----------|
| V.1.1 | 选择工作流 auto_film，输入"隔热膜价格"发送 | 用户/助手气泡显示，含时间戳；默认**非流式** |
| V.1.2 | 勾选聊天栏"流式"复选框再发消息 | 逐字流式显示（默认关闭，per-session 开关） |
| V.1.3 | 连发 3 条 | 消息区独立滚动，输入框贴底 |
| V.1.4 | 点"清空" | 弹出二次确认，确认后会话清空 |
| V.1.5 | 导出 JSON / CSV / Excel | 下载对应文件，**含 feedback/comment/correction 列**（本会话已提交的反馈） |
| V.1.6 | 停 FastAPI 后发消息 | 显示具体错误提示；重启后再发正常 |
| V.1.7 | 助手消息下点 👍 | 展开反馈框，可填评论；点"提交"后按钮高亮，toast "感谢反馈"；`feedback` 表新增 rating=up + comment |
| V.1.8 | 助手消息下点 👎 | 展开反馈框，含评论输入 + 纠错文本域；提交后记录 rating=down + comment + correction |
| V.1.9 | 最后一条助手消息点 🔄 重新生成 | 追加新一轮回答，turn_id 递增 |
| V.1.10 | 展开"会话信息"，填标题+标签(逗号分隔)，点保存 | toast "会话信息已保存"；`GET .../meta` 可见 title/tags |
| V.1.11 | 复制按钮 📋（所有助手消息） | 内容复制到剪贴板 |

### V.2 知识库浏览页 (KBBrowserPage)

| # | 操作 | 预期结果 |
|---|------|----------|
| V.2.1 | 选择集合 `car_film` | 分页显示文档点（id/source/text） |
| V.2.2 | 翻页 | offset 变化，内容切换 |
| V.2.3 | 搜索框输入"隔热" | 结果中"隔热"高亮（`<mark>`） |
| V.2.4 | 集合列表加载失败（停 Qdrant） | 应有错误提示（**已知缺陷**: 当前静默失败，下拉空白，见 improvement-plan.md） |

> ⚠️ 注: 当前"搜索"实为对首页 browse 结果的客户端高亮，**非语义检索**（improvement-plan.md P1-1）。测试时记录实际行为。

### V.3 工作流状态页 (WorkflowStatusPage)

| # | 操作 | 预期结果 |
|---|------|----------|
| V.3.1 | 展开 auto_film | dagre.js 渲染 DAG 拓扑，节点按层级排列 |
| V.3.2 | 点击节点 | 弹出该节点 YAML 配置 |
| V.3.3 | 查看 customer_service | 5 节点，含 if-then 分支标记 |
| V.3.4 | 修改 YAML `enabled: false` 后点"热重载" | 该工作流从列表消失；`/workflows` 返回数减少 |
| V.3.4b | 改回 `enabled: true` 再热重载 | 工作流恢复；选择框重新出现 |
| V.3.5 | 点"刷新"（不清缓存） | 与"重新载入"不同：仅重新拉取当前已注册列表 |
| V.3.6 | 热重载期间快速发对话请求 | 返回 503 "config reload in progress"，1 秒后恢复正常 |

### V.4 运行指标页 (MetricsPage)

| # | 操作 | 预期结果 |
|---|------|----------|
| V.4.1 | 打开"搜索过滤"折叠面板 | 工作流/节点名/工具名为**下拉菜单**（值来自 `/api/v1/sessions/filters`）；用户评价为下拉（全部/空/好评/差评）；时间/输入/输出/时长过滤项 |
| V.4.1b | 选工作流下拉 + 搜索 | **精确匹配**，只返回该工作流会话 |
| V.4.1c | 用户评价选"差评" | 只返回有 👎 反馈的会话；选"空"返回无任何评价的会话 |
| V.4.1d | 标题/标签列 | 会话表新增"标题/标签"列，显示 session_meta；聊天页保存过标题的会话显示标题 + 标签 chip |
| V.4.1e | 标题搜索 | 过滤面板输入"标题"关键词 → 只返回标题匹配的会话（持久化，会话过期后仍可搜） |
| V.4.2 | **仅填"节点"过滤后搜索** | 结果正常返回（回归 Layer S.2，前端不再报"搜索失败"） |
| V.4.3 | 仅填"输出文本"搜索 | 正常返回（回归 S.5） |
| V.4.4 | 列头点击排序 | 结果按列升/降序切换 |
| V.4.5 | 上一页/下一页 | 分页切换正常 |
| V.4.6 | 点击会话行 | 弹窗显示 DAG 执行状态（已执行绿/未执行灰）+ 输入/输出面板 |
| V.4.7 | 点击已执行节点 | 显示该节点输入/输出/工具调用详情 |
| V.4.8 | 下载会话 CSV | 下载 `sessions.csv` |

### V.5 文档管理页 (DocManagementPage)

| # | 操作 | 预期结果 |
|---|------|----------|
| V.5.1 | 选"新建"模式，输入集合名，上传 .md | 提示 chunks 数，入库成功 |
| V.5.2 | 上传 .pdf / .docx / .csv / .xlsx | 各格式被接受 |
| V.5.3 | 选"重建"模式，选已有集合 | **已知缺陷**: new/rebuild 均调同一端点，无 rebuild 参数（improvement-plan.md P1-2），记录实际行为 |
| V.5.4 | 一次选多个文件上传 | **已知缺陷**: 仅显示最后一个文件结果（improvement-plan.md P3），记录实际行为 |
| V.5.5 | 设置 chunk_size / chunk_overlap | 参数生效，chunk 数随之变化 |

### V.6 全局 UI

| # | 操作 | 预期结果 |
|---|------|----------|
| V.6.1 | 滚动页面 | 顶栏标题 + Tab 始终 sticky |
| V.6.2 | 侧边栏输入 API Key | 状态圆点变化（绿=连接/红=断开） |
| V.6.3 | 切换深色/浅色主题 | 主题切换生效（**已知缺陷**: 首次加载有 FOUC 闪烁，improvement-plan.md P2） |
| V.6.4 | 移动端/窄屏 | 布局响应式收缩 |
| V.6.5 | 刷新页面后 | **已知缺陷**: API Key 未持久化需重新输入（improvement-plan.md P2） |

---

## 反馈模板

```
Layer: [S / AF / V.x]
测试号: X.X
结果: [PASS / FAIL / 已知缺陷符合]
现象: <简短描述>
```

---

## Layer W · 2026-07-07 迭代新增（Wave 1–5）

> 覆盖：安全修复、聊天 UX、系统状态页、语义检索、文档重建、Metrics 平台化。

### W1 修复与安全

| # | 测试点 | 命令 / 操作 | 预期 |
|---|--------|-------------|------|
| W1.1 | code_exec 超时 | 让工作流走 code 工具执行 `while True: pass`（timeout=1） | ~1s 后返回 `TimeoutError`，不挂起 |
| W1.2 | 异常脱敏 | 触发一个内部 500（如 mock 故障） | 响应体为 `internal server error` + `request_id`，无堆栈/连接串 |
| W1.3 | 节点错误隔离 | 使某节点抛错后发请求 | 请求不返回 500 崩溃；`/sessions` 该会话 run 状态为 error，节点状态 error |
| W1.4 | 非破坏迁移 | 用旧 schema 的 metrics.db 启动 | 旧表被重命名 `*_backup_*`，历史仍在，新表可用 |
| W1.5 | Ollama 配置 | 不设 `OLLAMA_BASE_URL` 启动 | 走生产默认 `https://kaiwu.hix.ink/api/ollama/v1`；设该 env 可覆盖为 localhost |

### W2 聊天 UX

| # | 测试点 | 操作 | 预期 |
|---|--------|------|------|
| W2.1 | 默认不流式 | 清 localStorage 后打开聊天 | "流式" 复选框默认**未勾选** |
| W2.2 | Excel 导出 | 发几条消息 → 导出对话 → Excel | 下载 `chat_history.xlsx`，可用 Excel 打开，含 role/content/timestamp |
| W2.2b | CSV 导出 | 同上 → CSV | UTF-8 BOM，中文不乱码 |
| W2.3 | API 错误消息 | 停后端后发消息 | 提示含具体错误（非 "HTTP 400"） |
| W2.4 | 主题不闪烁 | 设深色主题 → 刷新页面 | 无浅色→深色闪烁 (FOUC) |
| W2.4b | API Key 持久化 | 输入 key → 刷新 | key 仍在，无需重输 |
| W2.5 | 清空确认 | 点"清空" | 弹确认框，取消则不清空 |
| W2.6 | Markdown 渲染 | 让助手回复含 `**粗体**`、`` `代码` ``、代码块 | 正确渲染格式与代码高亮块 |
| W2.7 | 快捷键 | Ctrl+Enter 发送；焦点不在输入框时按 `/` | 分别触发发送 / 聚焦输入框 |

### W3 核心功能

| # | 测试点 | 命令 / 操作 | 预期 |
|---|--------|-------------|------|
| W3.1 | 系统状态页 | 侧边栏 → 系统状态 | 显示 Qdrant/Ollama LLM/Embedding/Metrics/(DB池) 卡片 + 进程信息；整体状态 ok/degraded |
| W3.1b | /status 端点 | `Invoke-RestMethod http://$WIN_IP:9000/status` | 含 components + process(version/uptime/workflows) |
| W3.2 | 语义检索 | 知识库浏览 → 选 `car_film` → 搜索"隔热膜" | 返回**语义**结果（score 降序），命中词高亮 |
| W3.2b | 检索端点 | `/collections/car_film/search?q=隔热膜` | 200，points 含 text/score/source |
| W3.3 | 文档重建 | 文档管理 → 重建模式 → 选已有集合上传 | 响应 `rebuilt=true`，集合被先清空再重建 |
| W3.4 | 多文件结果 | 一次上传多个文件（含一个损坏） | 汇总显示成功 N/总数 + 失败明细 |
| W3.5 | Esc 关弹窗 | 聊天记录详情弹窗 → 按 Esc | 弹窗关闭 |

### W5 Metrics 平台化

| # | 测试点 | 命令 / 操作 | 预期 |
|---|--------|-------------|------|
| W5.1 | 仪表盘-总览 | 侧边栏 → 仪表盘 → 总览 | 首行全局概览卡片 + 按使用频率逐工作流区块（工作流指标 chip + 节点表 + 工具表，含 P95/错误率） |
| W5.1b | 仪表盘-图表 | 仪表盘 → 图表 → 选工作流 + 时间范围 | 折线图：活跃session/请求轮次(每分钟)/平均延迟/P95；节点与工具各 3 张多线图；自定义时间范围生效 |
| W5.2 | 摘要端点 | `/metrics/summary` | overview/by_workflow/by_tool/trend |
| W5.3 | 训练导出 | 聊天记录页 → 导出训练数据 / `/export/training.jsonl` | 下载 JSONL，每行含 `query/reply/feedback_rating/feedback_comment/feedback_correction`；`only_feedback=down` 仅导出差评样本 |
| W5.3b | 反馈审阅 | `GET /metrics/feedback?rating=down` | 返回差评列表，含 query/reply 上下文 |
| W5.8 | 仪表盘评价指标 | 仪表盘 → 总览 | 全局 + **每个工作流**均含三项：评价率 / 好评率 / 反馈率（含文字） |
| W5.9 | 反馈审阅（已移除 Tab） | 仪表盘不再有"反馈"Tab；反馈审阅改用 `/metrics/feedback` API 或聊天记录页评价过滤 |
| W5.10 | 好评率图表 | 仪表盘 → 图表 → 选工作流 | 工作流区含"好评率(%)"折线图 + "反馈量(👍/👎)"多线图 |
| W5.11 | RAG 检索详情 | 聊天记录 → 某含有 rag_search 的轮次 → 点 search_kb 节点 | 状态 Tab 显示 RAG 检索详情（N 条/平均分）+ 每条预览（score/collection/source/内容） |
| W5.12 | RAG 质量概览 | `GET /metrics/rag` | 返回 overview(avg_score/min/max) + by_collection + by_source |
| W5.13 | 成本报表 | 仪表盘 → 总览 | 全局 + 每个工作流含"费用（估算）"卡片（token×`pricing.yaml` 单价） |
| W5.4 | Token 统计 | 走一轮 LLM（供应商返回 usage）后查 `/api/v1/sessions/<id>` | turn 含 prompt_tokens/completion_tokens |
| W5.5 | 数据保留 | `POST /metrics/retention?days=1` | 返回 deleted_runs；旧记录被清 |
| W5.6 | 节点/工具指标 | `/metrics` | 含 `node_executions_total` / `node_duration_ms` / `tool_calls_total` / `workflow_runs_total` |
| W5.7 | 多引擎 | 设 `KF_METRICS_ENGINE=mysql` + 配置 db 池（见 metrics-db-setup.md） | 启动后自动建表，读写正常；默认不设仍用 SQLite |

---

## Layer X · 外部 API 分离 + 新增功能

> 外部 API 统一前缀 `/api/v1/`；旧 `/workflows`、`/sessions` 返回 404。

| # | 测试点 | 命令 / 操作 | 预期 |
|---|--------|-------------|------|
| X.1 | 路径迁移 | `GET /workflows`（旧） vs `GET /api/v1/workflows`（新） | 旧 404；新 200 返回列表 |
| X.2 | 外部健康 | `GET /api/v1/health`（无需 Key） | `{"status":"ok",...}` |
| X.3 | 内部健康仍在 | `GET /health` | 200，与 X.2 等价 |
| X.4 | 提交反馈 👍 | `POST /api/v1/sessions/{cid}/turns/0/feedback` body `{"rating":"up","comment":"好"}` | 200，返回 feedback_id |
| X.5 | 提交反馈 👎+纠错 | body `{"rating":"down","correction":"正确答案"}` | 200 |
| X.6 | 非法 rating | body `{"rating":"maybe"}` | 422 |
| X.7 | 查询反馈 | `GET /api/v1/sessions/{cid}/turns/0/feedback` | 返回 feedback 数组 |
| X.8 | 重新生成 | `POST /api/v1/workflows/auto_film/regenerate` body `{"chat_id":"{cid}"}` | 200，turn_id 递增，reply 为新回答 |
| X.9 | 重生成无会话 | chat_id 不存在 | 404 |
| X.10 | 会话元信息更新 | `PATCH /api/v1/sessions/{cid}/meta` body `{"title":"VIP","tags":["vip"]}` | 200，返回 title/tags |
| X.11 | 会话元信息查询 | `GET /api/v1/sessions/{cid}/meta` | 返回 title/tags/workflow/turn_id |
| X.12 | 用量查询 | `GET /api/v1/usage` | 返回 total_runs/total_sessions/total_tokens/error_rate |
| X.13 | 内部 API 未前缀化 | `GET /collections`、`/status`、`/metrics/summary` | 仍在原路径正常返回 |

### 反馈模板（同上）

```
Layer: W
测试号: WX.X
结果: [PASS / FAIL / 已知缺陷符合]
现象: <简短描述>
```
