# 下一步开发列表 (Next Development Roadmap)

> 跟踪表：勾选表示完成。优先级 P0(进行中) > P1 > P2 > P3。
> 关联：[`improvement-plan.md`](./improvement-plan.md)（Wave 1–5 已完成记录）。

## P0 · 数据库支持（本迭代，进行中）

- [x] **Metrics 多数据库实测** — 在 WSL 部署 MySQL + PostgreSQL，验证 `MySQLMetricsStore` / `PostgresMetricsStore` 真实读写
  - [x] WSL 部署 MySQL（docker `kf-mysql`，端口 3307）
  - [x] WSL 部署 PostgreSQL（docker `kf-pg`，端口 5433）
  - [x] 修复真实驱动下的 SQL 方言问题（TEXT 默认值→VARCHAR、CREATE INDEX IF NOT EXISTS、created_at 显式写入、RETURNING/lastrowid、group_concat/string_agg）
  - [x] 集成测试：三引擎跑通 insert/search/aggregate/timeseries/feedback/export（`tests/test_db_integration.py`，10 项）
  - [x] `KF_METRICS_ENGINE=mysql|postgresql` 全链路切换验证（工厂 + 连接池 + 读写）
- [x] **db_query 工具真实连库** — MySQL/PG 均可连接并执行参数化查询
  - [x] 修复 `PgPool.execute`（DDL/INSERT "no results to fetch" + 缺 commit）
  - [x] 修复 `MySQLPool.execute`（缺 commit，写入未持久化）
  - [x] `db_query` 端到端：参数化查询 + `{{query}}` 占位符 + 中文，写入可持久化
  - [x] 集成测试覆盖（`test_db_integration.py::TestDBQueryToolRealDB`）

## P1 · 反馈功能 GUI 收尾

- [x] Dashboard 总览新增「好评率」卡片（👍/👎 计数 + satisfaction_rate）
- [x] 反馈审阅界面（Dashboard「反馈」Tab，按 rating/工作流过滤，展示 query/reply/评论/纠错）

## P1 · 可靠性

- [x] rag_search 全局 Qdrant/Embed 客户端**重连机制**（embed 失败重置重试；全集合失败重置 Qdrant）
- [x] 并行分支内 `if-then` 路由语义修复（`_walk_branch` 按 branch 选单一路径）

## P2 · 一致性 / 技术债

- [x] 新增 `config/qdrant.yaml`（+ `QdrantConfig` 配置类，`_make_qdrant`/rag_search 读取，env 可覆盖）
- [x] 模板解析抽公共工具（W4-4）— `src/engine/tools/_template.py::resolve_template`，4 个工具委托，统一占位符能力
- [x] `db_query` 模板已支持 `{{chat_id}}`/`{{_workflow}}`/`{{return_mode}}`/`{{long_mem_data}}`/`{{data_map}}`（审计误报，实为已支持）

## P3 · 产品功能（较大）

- [x] ~~多租户配额（`/api/v1/usage` 目前全局，无 API Key 维度）~~ — 已划掉，暂不做
- [x] RAG 检索详情入库（`rag_retrievals` 表 + 数据采集 + API/GUI）
- [x] 成本报表（`config/pricing.yaml` + `_compute_cost` + 仪表盘费用卡片/每工作流费用）
- [x] 会话 title/tags 持久化到 metrics + GUI（`session_meta` 表；PATCH/GET meta 双写；聊天记录页显示标题/标签列 + 标题搜索）

## ⚙️ 运维 / 生产

- [ ] CI/CD 流水线
- [ ] K8s 部署验证（ACK）
