# 项目改进计划 (Improvement Plan)

> 生成日期: 2026-07-07 | 基于全项目检查 (git v1 / commit 27904b9)
> 测试状态: 432 passed (`.venv` Python 3.12.9)
>
> **实施状态（2026-07-07 迭代）**：Wave 1–5 已全部实现，见文末路线图勾选。

本文档记录当前项目未完成工作、可提升项与可新增功能，按优先级排序。

> 部分项本轮不做，见 [`deferred.md`](./deferred.md)。

---

## P0 — 立即处理（安全）

| # | 项 | 位置 | 说明 |
|---|-----|------|------|
| 1 | code_exec timeout 无效 | `src/engine/tools/code_exec.py:103` | `timeout` 参数文档化但从未生效；`exec()` 无超时机制，`while True` 会永久挂起 worker 线程 |
| 2 | 异常细节泄露 | `src/api/main.py:131-136` | 全局异常处理器将 `str(exc)` 直接返回客户端，泄露内部细节（LLM 错误、连接串等） |

---

## P1 — 未完成的工作

| # | 项 | 位置 | 说明 |
|---|-----|------|------|
| 1 | 知识库"搜索"是假的 | `src/gui/ui/src/pages/KBBrowserPage.vue:90` | `doSearch()` 未传 query，只对首页 browse 结果做客户端高亮，未接语义检索端点 |
| 2 | DocMgmt "重建"未实现 | `src/gui/ui/src/pages/DocManagementPage.vue:19` | new/rebuild 只切换输入框样式，都调用同一上传端点，无 `rebuild` 参数 |
| 3 | 执行 trace 被丢弃 | `src/api/main.py:279,333` | DAG 跑完立即 `session.nodes.clear()`，指标追踪数据丢失 |
| 4 | 节点错误无隔离 | `src/engine/dag.py:510` | `_run_tool` 无异常处理，任一节点抛错整个 DAG 崩 500，无部分结果恢复 |
| 5 | 配置未对齐生产 | `config/llm.yaml`, `config/embed.yaml` | 仍指向 `localhost:11434`，与 AGENTS.md 生产 Ollama URL (`https://kaiwu.hix.ink/api/ollama`) 不符 |
| 6 | 破坏性 schema 迁移 | `src/metrics/store.py:39-43` | 使用 `DROP TABLE IF EXISTS`，升级 schema 时静默丢失历史指标数据 |

---

## P2 — 可提升的质量

### 后端
- **静默吞异常** (7 处): `qdrant.py:168`, `rag_search.py:101,150`, `session/data.py:303`, `logger/__init__.py:183` 等 `except: pass`，调试极困难 → 应记录日志
- **模板解析重复** (6 处): `llm_tool.py:114`, `db_query.py:118`, `web_search.py:147`, `api_call.py:101`, `code_exec.py:188` + extract 系列各自实现 `{{query}}` 占位符替换 → 抽公共工具（省 ~80 行）
- **MetricsStore 无连接池** (`src/metrics/store.py`): 每次操作开关一次 SQLite 连接，单次 DAG 跑约 8 次连接；且无 `try/finally` 保护
- **DB pool 重复代码**: `mysql_pool.py` / `pg_pool.py` 90% 相同 → 抽 `QueuePool` 基类，驱动特定钩子
- **env 变量名不一致**: `DEEPSEEK_API_KEY` (llm.yaml/.env) vs `DEEPSEEK_KEY` (session.yaml:24) → 摘要压缩永远找不到 key
- **HTTP client 泄露**: `llm/client.py` 与 `rag_search.py` 全局 client 从不 `close()`，长跑进程 socket 泄露
- **rag_search 懒初始化竞态** (`rag_search.py:72-79`): 并发线程可能重复创建 `_embed_client` → 加 `threading.Lock`
- **DB 连接回收隐患** (`mysql_pool.py:143`, `pg_pool.py:134`): ping 失败仍把坏连接放回池
- **requirements.txt** 是 pip freeze 转储（99 项，含被禁的 `watchfiles`）→ 以 `pyproject.toml` 为准
- **config 重复 router 规则**: `customer_service/intent_classify.yaml:34,40` "你好" 规则重复
- **未编码 URL 注入风险**: `customer_service/order_handler.yaml:2` 原始 `{{query}}` 直插 URL 路径

### 前端
- **主题 FOUC 闪烁**: `index.html` 硬编码 `data-theme="light"`，onMounted 后才切换 → 应在 `<head>` 阻塞脚本读 localStorage
- **API 错误只显示 "HTTP 400"** (`src/api.js:27,44,54`): 未读取服务端 JSON 错误体
- **无 Vite dev proxy** (`vite.config.js`): `npm run dev` (5173) 调 API 会 404，需代理到 9000
- **API key 不持久化** (`store.js:16`): 每次会话需重新输入
- **静默吞异常** (6 处前端 `catch(_){}`): DocMgmt/KBBrowser collections 加载失败时页面空白无提示
- **潜在 XSS** (`MetricsPage.vue:283`): `highlightJSON` 非 JSON 回退路径未转义，经 `v-html` 渲染
- **N+1 请求瀑布** (`MetricsPage.vue:241`): session 详情串行拉取每个 turn，无 `Promise.all`
- **无 API 超时** (`src/api.js`): 除 health 外裸 `fetch`，后端挂起则 spinner 永转
- **缓存永不刷新**: WorkflowStatus/Metrics 页模块级缓存，工作流变更需刷新整个浏览器
- **dagre.min.js 未纳入构建**: 靠手动拷贝，缺失则 DAG 静默空白

---

## P3 — 可添加的功能

- **真·语义检索** 接入知识库浏览页
- **聊天 Markdown 渲染** + 代码高亮（LLM 场景刚需，`ChatPage.vue` 当前纯文本）
- **聊天默认不流式**：`ChatPage` `useStream` 恒初始化为 `false`（已移除 `streamDefault` 持久化与侧边栏开关），流式改为聊天页 per-session 复选框
- **聊天记录导出 CSV / Excel**：`ChatPage.vue` 当前有 JSON/CSV 导出，补充 Excel(.xlsx) 导出（复用 `openpyxl`）
- **系统状态页面**：新增 Tab 显示系统整体健康 + 各下游组件健康（FastAPI `/health`、`/ready`；Qdrant、Ollama LLM、Ollama Embedding、DB 连接、Metrics 存储的连通性/延迟/版本），后端扩展 `/ready` 或新增 `/status` 聚合端点
- **DAG 节点级错误恢复** + 部分结果返回
- **执行 trace 持久化** 到 metrics（当前被 clear 清空）
- **拖拽上传** + 多文件批量结果汇总（`DocManagementPage.vue:108` 当前只显示最后一个结果）
- **工作流热重载**（`POST /reload` + enabled 字段 + 请求冲突保护）
- **键盘快捷键**: Ctrl+Enter 发送、Esc 关闭弹窗、`/` 聚焦输入
- **清空对话二次确认**（`ChatPage.vue:9` 当前一键不可逆）
- **Qdrant 配置文件** `config/qdrant.yaml`（当前仅靠 env 变量，与其他服务不一致）

### Metrics 多数据库引擎适配（MySQL / PostgreSQL）

> ⚠️ 备注：**当前仍使用现有引擎（SQLite），本项仅规划，暂不切换。**

`src/metrics/store.py` 目前硬编码 SQLite（`sqlite3.connect`）。规划将其抽象为可插拔引擎，通过配置文件选择：

- **配置驱动引擎选择**：新增/扩展配置（如 `config/metrics.yaml` 或复用 `config/db.yaml`），字段 `engine: sqlite | mysql | postgresql`，默认 `sqlite`（保持现状）。
- **存储层抽象**：抽 `MetricsStore` 接口，SQLite 实现保留为默认；新增 `MySQLMetricsStore` / `PostgresMetricsStore` 实现，复用已有 `src/db/mysql_pool.py` / `src/db/pg_pool.py` 连接池。
- **SQL 方言差异处理**：
  - 自增主键：SQLite `AUTOINCREMENT` → MySQL `AUTO_INCREMENT` → PG `SERIAL`/`IDENTITY`
  - 时间函数：`datetime('now')` → MySQL `UTC_TIMESTAMP()` → PG `NOW() AT TIME ZONE 'UTC'`
  - 占位符：`?` (SQLite) → `%s` (MySQL/PG)
  - 子串匹配：`LIKE` 保持；PG 大小写不敏感可选 `ILIKE`
  - `search_sessions` 的子查询、`GROUP_CONCAT`（PG 用 `string_agg`，MySQL 用 `GROUP_CONCAT`）需按方言适配
- **依赖**：MySQL 用 `PyMySQL`、PG 用 `psycopg2-binary`（均已在 `requirements.txt` 中，属新增依赖需按 AGENTS.md 手动确认）。
- **安装配置文档**（需新建）：
  - `docs/metrics-db-setup.md` — 三引擎的建库/建表/建索引 SQL、连接配置示例、迁移步骤
  - MySQL：字符集 `utf8mb4`、时区、用户授权
  - PostgreSQL：数据库/schema 创建、`timestamptz` 说明、连接串
  - 从 SQLite 迁移历史指标数据的脚本/步骤（可选）
- **测试**：`tests/test_metrics.py` 参数化覆盖三引擎（CI 可用 mock 或 docker 服务）。

### Metrics 功能路线图

> 现状：SQLite 三层存储（runs→node_logs→tool_logs）、`/sessions` 多条件搜索、会话详情 DAG 执行追踪（含 IN/OUT + 状态 Tab）、4 个 Prometheus 指标、会话级 CSV 导出。

**一、数据采集增强**
- 完整执行 trace 持久化（当前 `session.nodes.clear()` 丢弃工具级细节，见 P1-3）
- Token 用量统计：每次 LLM 调用 prompt/completion tokens + 成本估算
- LLM 请求快照：完整 prompt、temperature、模型名、供应商，便于复现
- 路由决策记录：router 命中的 branch 与匹配规则，分析意图分类准确率
- RAG 检索详情：召回 chunk、score、命中 collection，评估检索质量
- 用户反馈：👍/👎、纠错标注（为微调/评估打标签）

**二、聚合与分析**
- 仪表盘概览：QPS、平均/P50/P95/P99 延迟、错误率、活跃会话数
- 工作流维度统计：各 workflow 调用量、成功率、平均耗时对比
- 节点/工具热力：最慢节点 Top N、最常失败工具、耗时分布直方图
- 时间趋势图：按小时/天的调用量、延迟、错误率折线
- 意图分布：各意图分类占比、非产品问题拒答率（auto_film 场景）
- 成本报表：按 workflow/时间段的 token 消耗与费用

**三、可视化**
- 图表化（当前纯表格）：延迟趋势、分布直方图、DAG 路径桑基图
- 失败会话快速筛选：一键过滤 status=error，看错误堆栈
- 会话对比：并排看两次执行的 DAG 路径差异
- 实时监控视图：SSE/轮询刷新最新会话

**四、导出与集成**
- 训练数据导出：按标签/质量筛选导出 JSONL（微调用）
- 节点级 CSV/JSON 导出（当前仅会话级）
- OpenTelemetry / Jaeger 分布式 tracing 对接
- Grafana 数据源：扩展 Prometheus 指标（当前仅 4 个，缺节点/工具级指标）
- 告警：错误率/延迟超阈值触发（AlertManager，`k8s/prometheus-rules.yaml` 已有雏形）

**五、运维与可靠性**
- 多数据库引擎（见上节 MySQL/PG 适配）
- 数据保留策略：TTL 自动清理旧记录、分区/归档
- 连接池（见 P2：当前每操作开关连接）
- 非破坏性 schema 迁移（见 P1-6：当前 `DROP TABLE`）
- 异步写入：指标落库不阻塞请求主链路（队列/后台线程）

**六、数据质量（面向训练）**
- 去重/相似会话聚类
- 自动质量评分：基于回复长度、是否命中 RAG、是否拒答
- 人工标注工作台：在 GUI 直接标注好坏样本

---

## 执行路线（按优先级分波次）

> 上方 P0–P3 为**问题目录**（按性质分类）；下方为**执行顺序**（按价值/成本/依赖重排）。每波可独立交付。

### Wave 1 — 修复与安全（最高优先，本迭代必做）
1. ✅ P0-1 `code_exec` 超时防挂起（线程 + best-effort 中断）
2. ✅ P0-2 异常细节脱敏（返回 request_id，堆栈仅入日志）
3. ✅ P1-4 节点错误隔离（`_run_tool` try/except，错误状态入 metrics）
4. ✅ P1-6 非破坏性 schema 迁移（旧表重命名备份）
5. ✅ P1-5 配置对齐生产 Ollama URL（env 默认值 + `${VAR:-default}` 支持）

### Wave 2 — 低成本高价值的用户可感知改进
1. ✅ 聊天默认不流式（`useStream=false`，后移除 `streamDefault` 持久化与侧边栏开关）
2. ✅ 聊天记录导出 CSV / Excel（后端 openpyxl `/export/chat.xlsx|csv`）
3. ✅ API 错误显示服务端消息（`toError` 读 detail）
4. ✅ 主题 FOUC 修复（head 阻塞脚本）+ API key 持久化
5. ✅ 清空对话二次确认
6. ✅ 聊天 Markdown 渲染 + 代码高亮（`md.js`）
7. ✅ 键盘快捷键（Ctrl+Enter 发送、`/` 聚焦、Esc 关弹窗）

### Wave 3 — 核心功能补全
1. ✅ 系统状态页面（`/status` 聚合端点 + `StatusPage.vue`）
2. ✅ P1-3 执行 trace 持久化（确认 metrics 先于 clear；补错误状态/token）
3. ✅ P1-1 真语义检索（`/collections/{name}/search` + KB 页接入）
4. ✅ P1-2 DocMgmt 重建（`rebuild` 参数，先删集合）
5. ✅ 前端：静默异常提示、缓存刷新按钮、N+1 并行化、API 超时
6. ✅ 工作流热重载（`POST /reload` + `enabled` 字段 + 中间件 503 冲突保护）

### Wave 4 — 稳定性与技术债
1. ✅ 后端静默吞异常 → 日志化（qdrant/rag_search/session）
2. ✅ MetricsStore 连接上下文管理器（try/finally）
3. ✅ rag_search 懒初始化加锁 / DB 连接回收（坏连接丢弃）
4. ⏭️ 模板解析抽公共工具 / DB pool 抽基类（低优先，纯重构，留后续）
5. ✅ config 重复 router 规则清理、env 变量名统一（DEEPSEEK_API_KEY）
6. ✅ Vite dev proxy、dagre 随 `public/` 构建

### Wave 5 — Metrics 平台化
1. ✅ 仪表盘概览 + 趋势 + 节点/工具热力（`MetricsPage` 仪表盘 + `/metrics/summary`）
2. ✅ Token 用量统计（LLM usage → runs.prompt/completion_tokens）
3. ✅ 数据保留（`/metrics/retention` + `delete_older_than`）
4. ✅ 训练数据导出 JSONL（`/export/training.jsonl`）
5. ✅ 多数据库引擎适配（SQLite/MySQL/PG + factory + `docs/metrics-db-setup.md`）
6. ✅ Grafana 面板 + 节点/工具 Prometheus 指标 + 告警规则（OTel 经 Collector 抓取 `/metrics`）

> 说明：唯一未做项为 Wave 4-4（模板解析/DB pool 纯重构），无功能影响，标记为后续技术债。
