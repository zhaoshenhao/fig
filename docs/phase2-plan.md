# 第二阶段任务表

> 第一阶段交付状态: ruff 零警告 | 314 tests passed | 96.16% 覆盖率 | 11 篇文档 | 27 个源文件中文注释
> 补充交付 (2026-07-03): 知识库多格式入库 (CSV/XLSX/HTML) + 自动检测 + 知识库管理 CLI/API

---

## 一、功能类

| # | 任务 | 优先级 | 预估工时 | 说明 |
|---|------|--------|---------|------|
| 1 | **Streamlit DAG 拓扑可视化** | P2 | 4h | 工作流 Tab 中展示节点依赖关系图（`next_type`/`next`/`parallel`），点击节点查看 YAML 配置；可复用 `validate_workflow.py` 中的 `_build_graph` 生成 adjacency |
| 2 | **多轮对话后处理** | P2 | 3h | chat 历史导出 (JSON/CSV)、会话维度统计 (情绪/意图/满意度)，可集成 LLM 做会话摘要 |
| 3 | **文件上传格式扩展** | P1 | 6h | 支持 PDF (pymupdf)、docx (python-docx)、图片 OCR (tesseract/paddleocr)；`chunker.py` 已有 PDF/docx 解析代码，需补 CLI 和 API 入口 |
| 4 | **API 版本号 + 变更日志** | P3 | 2h | `/v2/workflows/...` 路由前缀 + CHANGELOG.md；breaking change 需向后兼容代理 |
| 5 | **WebSocket / SSE 流式回复** | P1 | 8h | WebSocket 端点 `ws://host/workflows/{name}/run` 或 SSE 端点推送 token-by-token LLM 输出；替代当前阻塞式 wait；需改 `LLMClient.chat` 支持 stream |
| 6 | **工作流配置热更新** | P2 | 3h | 检测 `config/workflows/` 目录变化 (轮询 10s 或 fsnotify)，自动调用 `load_app_config()` 刷新；需确保并发安全（加写锁） |

## 二、测试与质量

| # | 任务 | 优先级 | 预估工时 | 说明 |
|---|------|--------|---------|------|
| 7 | **E2E 集成测试** | P1 | 6h | `docker-compose up` 后跑端到端用例：创建 session → POST run → 校验 reply/chat_id/turn_id；用 `testcontainers` 启动 Qdrant/Ollama 容器 |
| 8 | **压力测试** | P2 | 4h | locust/k6 脚本：并发 50/100/200，测 p50/p95/p99 延迟、错误率、内存泄漏；目标 1000 QPS 下 p95 < 2s |
| 9 | **Redis 存储集成测试** | P2 | 2h | `testcontainers` 启动 Redis，跑 `test_session_store.py` 的 Redis 用例；验证 TTL 自动过期行为 |

## 三、运维与部署

| # | 任务 | 优先级 | 预估工时 | 说明 |
|---|------|--------|---------|------|
| 10 | **K8s 配置模板化** | P1 | 4h | 用 Helm chart 或 kustomize overlay 替换 `<NAMESPACE>`/`<ACR_REGISTRY>` 等占位符；支持 dev/staging/prod 三环境 overlay |
| 11 | **Grafana 仪表盘 JSON** | P2 | 3h | 预构建 KF 业务监控仪表盘：QPS/延迟热力图、LLM 调用量/错误率趋势、RAG 检索延迟分位图、会话活跃数；导出 JSON 到 `k8s/grafana-dashboard.json` |
| 12 | **CI/CD pipeline** | P1 | 4h | GitHub Actions: lint → test → build image → push to ACR → deploy to ACK；或 ACK OneFlow/devops pipeline |
| 13 | **日志轮转策略** | P3 | 2h | 本地开发时 JSON 日志写入文件 `data/logs/kf.log` 并按天轮转 (保留 7 天)；生产环境 stdout 不变 |

## 四、安全

| # | 任务 | 优先级 | 预估工时 | 说明 |
|---|------|--------|---------|------|
| 14 | **速率限制中间件** | P1 | 3h | 按 IP / chat_id 限流 (token bucket 算法)；配置 `config/rate-limit.yaml`: `{window: 60s, max: 100}`；`/health` `/metrics` 跳过 |
| 15 | **SQL 注入防护增强** | P2 | 2h | `db_query.py` 校验 SQL 白名单 (禁止 UPDATE/DELETE/DROP/ALTER)；白名单表名列表；参数化查询审计日志 |
| 16 | **敏感信息加密存储** | P3 | 2h | `config/auth.yaml` 中 `api_keys` 用 AES-256-GCM 加密替代明文；启动时从 K8s Secret 读取解密密钥 |

## 五、优先级总览

```
P1 (高优先) : #3 文件格式扩展 / #5 流式回复 / #7 E2E 测试 / #10 K8s 模板化 / #12 CI/CD / #14 速率限制
P2 (中优先) : #1 DAG 可视化 / #2 对话后处理 / #6 热更新 / #8 压力测试 / #9 Redis 测试 / #11 Grafana / #15 SQL 防护
P3 (低优先) : #4 API 版本 / #13 日志轮转 / #16 密钥加密
```

| 优先级 | 项数 | 总预估工时 |
|--------|------|-----------|
| P1 | 6 | 31h |
| P2 | 7 | 21h |
| P3 | 3 | 6h |
| **合计** | **16** | **58h** |
