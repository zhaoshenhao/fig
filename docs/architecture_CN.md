[English](architecture_EN.md)

# KF 智能客服系统 — 架构文档

## 系统架构

系统采用六层分层架构设计，从用户界面到底层基础设施逐层解耦。

### 第一层 — 表现层（Presentation）

| 组件 | 技术栈 | 部署方式 | 状态 |
|------|--------|----------|------|
| Vue 3 SPA | Vue 3 + Vite + dagre.js | 阿里云 OSS + CDN 分发 | 主力 |
| Streamlit 调试 GUI | Streamlit（`src/gui/app.py`） | 开发环境本地运行 | 遗留（已替换） |

Vue SPA 通过 Vite 开发代理 `/api/v1` → 本地 FastAPI（端口 9000），生产环境走 ALB Ingress 分流。

### 第二层 — API 网关（API Gateway）

应用入口：`src/api/main.py`，FastAPI 应用工厂模式。

**KF_MODE 双模式部署**：
- `KF_MODE=chat`：加载用户流量路由（`routes_chat.py`）
- `KF_MODE=admin`：加载管理后台路由（`routes_admin.py`）
- `KF_MODE=full`（默认）：同时加载两组路由

**中间件栈**（按注册顺序）：
```
CharsetMiddleware → CORS → RequestID → Metrics → Auth (X-API-Key)
```

**端点清单**：

| 端点 | 方法 | 所属路由组 | 说明 |
|------|------|-----------|------|
| `/health` | GET | 始终可用 | 存活探针，返回启动耗时 |
| `/ready` | GET | 始终可用 | 就绪探针，检查 Qdrant / Embedding / DB 连通性 |
| `/status` | GET | 始终可用 | 组件状态总览（LLM / Embedding / DB / Qdrant / Metrics） |
| `/metrics` | GET | 始终可用 | Prometheus 指标输出（text/plain） |
| `/reload` | POST | 始终可用 | 热重载配置文件（不重启进程） |
| `/api/v1/workflows/{name}/run` | POST | chat | 工作流执行（核心入口） |
| `/api/v1/sessions/*` | GET/DELETE/PATCH | chat | 会话管理 CRUD |
| `/api/v1/sessions` | GET | admin | 管理员会话搜索（带多条件过滤） |
| `/collections/*` | GET/POST/PUT/DELETE | admin | Qdrant 集合管理 |
| `/documents/*` | POST/PUT/DELETE | admin | 文档上传与管理 |
| `/export/*` | GET | chat | 对话导出 |

**异常处理**：全局 `Exception` 捕获 → 统一 JSON 500 响应，含 `request_id` 用于链路追踪。

**配置重载门控**：`/reload` 期间其他请求返回 503 + `Retry-After: 1`。

### 第三层 — 工作流引擎（Workflow Engine）

位置：`src/engine/`

**DAGEngine**（`dag.py`）：
- 基于 `deque` 的 BFS 拓扑遍历
- 条件分支：`next_type=if-then`，根据节点输出选择后继路径
- 并行分支：`next_type=switch`，`ThreadPoolExecutor` 并发执行各分支，`merge` 工具汇聚结果
- 会话状态追踪：`session.nodes` 记录所有已执行节点的输入/输出，供下游节点引用
- 指标采集：每次执行后自动调用 `_collect_metrics` 收集完整执行轨迹

**ToolRegistry**（`tool.py`）：
- 可插拔工具系统，键值对存储（名称 → 函数）
- 统一工具签名：`fn(config: dict, session: SessionData) -> dict`

**10 个内置工具**：

| 工具 | 文件 | 功能 |
|------|------|------|
| `llm` | `llm_tool.py` | LLM 对话生成（支持 system / user / assistant 消息模板） |
| `rag_search` | `rag_search.py` | 知识库检索（混合向量 + BM25，RRF 融合） |
| `router` | `router.py` | 条件路由（exact / regex / contains 匹配，intent 映射） |
| `merge` | `merge.py` | 并行分支结果合并 |
| `db_query` | `db_query.py` | SQL 查询（LLM 生成 SQL → 执行 → LLM 总结） |
| `extract_llm` | `extract_llm.py` | LLM 结构化信息抽取 |
| `extract_regex` | `extract_regex.py` | 正则表达式信息抽取 |
| `api_call` | `api_call.py` | 外部 API 调用（HTTP 代理） |
| `web_search` | `web_search.py` | 网络搜索（搜索引擎集成） |
| `code` | `code_exec.py` | 代码执行（沙箱化 Python 执行） |

### 第四层 — 领域服务（Domain Services）

**会话管理**（`src/session/`）：

| 模块 | 职责 |
|------|------|
| `data.py` | `SessionData`（dataclass，类字典协议）+ `TurnRecord` + `trim_or_compress` 两阶段裁剪/压缩 |
| `base.py` | `SessionStore` 抽象基类 |
| `memory.py` | `MemorySessionStore`（dict 存储，开发/单机用，支持 TTL 清理线程） |
| `redis_store.py` | `RedisSessionStore`（Redis 存储，多 Worker 共享，生产环境） |

裁剪/压缩策略：TTL 过期裁剪 + LLM 摘要压缩，保持会话上下文在 token 窗口内。

**LLM 客户端**（`src/llm/client.py`）：
- `LLMClient` 类，基于 `httpx2.Client`，OpenAI 兼容 API
- 支持 `chat`（同步）和 `stream_chat`（SSE 流式）两种调用模式
- 支持 OpenAI / Anthropic 两种 provider type，统一接口

**RAG 检索**（`src/rag/qdrant.py`）：
- `QdrantSearch` 门面类，封装 Qdrant gRPC 客户端（`prefer_grpc=True`，端口 6334）
- 混合检索：Dense Vector（768d Cosine）+ Sparse BM25 + RRF 分数融合
- 自动降级：混合检索失败时回退纯向量检索
- 集合管理：`ensure_collection`、`upsert`、`scroll`、`count`

### 第五层 — 数据与存储（Data & Storage）

**DB 连接池**（`src/db/`）：
- `base.py`：`DBConfig` / `DBPoolConfig` 配置模型，`DBPool` 抽象基类
- `mysql_pool.py`：MySQL 连接池（pymysql）
- `pg_pool.py`：PostgreSQL 连接池（psycopg2）
- 配置驱动：`config/db.yaml` 定义连接池，按名称引用

**Metrics 存储**（`src/metrics/`）：

三层执行追踪结构：
```
runs（会话轮次）→ node_logs（节点执行）→ tool_logs（工具调用）
```

| 模块 | 职责 |
|------|------|
| `schema.py` | 表 DDL 规范定义（唯一权威来源） |
| `migration.py` | 版本化迁移（`Migration` 数据类 + `MIGRATIONS` 列表，启动时自动执行） |
| `dialect.py` | 多数据库方言适配（SQLite / MySQL / PostgreSQL） |
| `store.py` | `MetricsStore`（SQLite 实现） |
| `sql_store.py` | `SQLMetricsStore`（MySQL/PostgreSQL 生产实现） |
| `factory.py` | `create_metrics_store()` 工厂函数 |
| `prometheus.py` | Prometheus 指标导出（Counter / Histogram / Gauge） |

**外部存储**：
- **Qdrant**：外部 Docker 容器，gRPC 端口 6334，Dense 768d + Sparse BM25 双索引
- **kf-embed**：独立 FastEmbed/ONNX 微服务（`src/embed_service/app.py`），端口 8100，OpenAI 兼容 `/v1/embeddings`

### 第六层 — 基础设施（Infrastructure）

**本地开发**（`docker-compose.yaml`）：
```
embed (8100) + qdrant (6333/6334) + api (8000)
```

**Kubernetes 生产部署**：

| 资源 | 类型 | 说明 |
|------|------|------|
| chat-api | Deployment | 用户流量，`KF_MODE=chat` |
| admin-api | Deployment | 内部管理，`KF_MODE=admin` |
| kf-embed | Deployment | FastEmbed ONNX 向量化（1 副本，模型烘焙进镜像） |
| Qdrant | StatefulSet | 向量数据库（EBS/ESSD 持久化） |

同一 Docker 镜像（`Dockerfile`）构建 chat-api 和 admin-api，通过 `KF_MODE` 环境变量区分路由组。

**外部托管服务**：
- DeepSeek API：LLM 推理
- Redis：会话共享存储（多 Worker 一致性）
- MySQL RDS：Metrics 主库
- PostgreSQL RDS：分析数据库
- 阿里云 OSS：配置文件（CSI PVC 挂载）+ SPA 静态文件（CDN 分发）

---

## 目录结构

```
kf/
├── config/                          # YAML 配置文件
│   ├── auth.yaml                    # API 密钥 + 鉴权跳过路径
│   ├── db.yaml                      # 数据库连接池配置
│   ├── embed.yaml                   # Embedding 服务提供商配置
│   ├── gui.yaml                     # Streamlit GUI 配置
│   ├── llm.yaml                     # LLM 提供商配置
│   ├── logging.yaml                 # 日志级别配置
│   ├── metrics.yaml                 # Metrics 存储配置
│   ├── pricing.yaml                 # 定价配置
│   ├── qdrant.yaml                  # Qdrant 连接配置
│   ├── session.yaml                 # 会话管理配置
│   └── workflows/                   # 工作流定义
│       ├── auto_film/               # 汽车膜产品工作流
│       │   ├── workflow.yaml        # DAG 拓扑定义
│       │   └── nodes/               # 节点 YAML 配置
│       ├── customer_service/        # 客服产品工作流
│       └── default/                 # 默认工作流
├── src/                             # 源代码
│   ├── api/                         # FastAPI 应用层
│   │   ├── main.py                  # 应用工厂、生命周期、路由注册
│   │   ├── state.py                 # 单例 getter/setter（全局状态管理）
│   │   ├── auth.py                  # X-API-Key 认证中间件
│   │   ├── routes_chat.py           # 用户流量路由（workflows / sessions）
│   │   └── routes_admin.py          # 管理后台路由（metrics / collections / documents）
│   ├── cli/                         # CLI 命令行工具
│   │   ├── build.py                 # 文档入库 CLI
│   │   ├── manage.py                # 知识库管理 CLI
│   │   └── validate_workflow.py     # 工作流校验器
│   ├── config.py                    # 配置加载器（AppConfig 单例，YAML + ${ENV_VAR} 插值）
│   ├── db/                          # 数据库连接池
│   │   ├── base.py                  # DBConfig / DBPoolConfig / DBPool 抽象基类
│   │   ├── mysql_pool.py            # MySQLPool（pymysql）
│   │   └── pg_pool.py               # PgPool（psycopg2）
│   ├── embed_service/               # kf-embed 向量化微服务
│   │   ├── app.py                   # FastAPI 应用（端口 8100）
│   │   └── service.py               # Embedding 服务逻辑（FastEmbed 封装）
│   ├── engine/                      # DAG 工作流引擎
│   │   ├── dag.py                   # DAGEngine（拓扑遍历、并行分支、指标采集）
│   │   ├── tool.py                  # ToolRegistry（可插拔工具注册表）
│   │   └── tools/                   # 内置工具集
│   │       ├── _template.py         # 工具开发模板
│   │       ├── llm_tool.py          # LLM 对话生成
│   │       ├── rag_search.py        # 知识库检索（RAG）
│   │       ├── router.py            # 条件路由（exact / regex / contains）
│   │       ├── merge.py             # 并行分支结果合并
│   │       ├── db_query.py          # 数据库查询（LLM SQL 生成 + 执行）
│   │       ├── extract_llm.py       # LLM 结构化抽取
│   │       ├── extract_regex.py     # 正则表达式抽取
│   │       ├── api_call.py          # 外部 API 代理调用
│   │       ├── web_search.py        # 网络搜索引擎集成
│   │       └── code_exec.py         # 代码沙箱执行
│   ├── gui/                         # Streamlit 调试 GUI（遗留）
│   │   ├── app.py                   # Streamlit 主入口
│   │   ├── ui/                      # Vue 3 + Vite SPA 源码
│   │   └── utils.py                 # GUI 工具函数
│   ├── ingestion/                   # 文档入库管道
│   │   ├── chunker.py               # 文本分块器
│   │   └── builder.py               # 文档构建器（分块 → 向量化 → 写入 Qdrant）
│   ├── llm/                         # LLM 客户端
│   │   └── client.py                # 统一 REST API 客户端（chat + embed，httpx2）
│   ├── logger/                      # 结构化日志
│   │   ├── __init__.py              # JSONFormatter + init_logging（按模块配置级别）
│   │   └── middleware.py            # RequestID 注入中间件
│   ├── metrics/                     # 可观测性
│   │   ├── schema.py                # 表结构规范定义（DDL 唯一权威来源）
│   │   ├── migration.py             # 版本化数据库迁移（启动时自动执行）
│   │   ├── dialect.py               # 多数据库 SQL 方言适配
│   │   ├── store.py                 # MetricsStore（SQLite 实现，开发用）
│   │   ├── sql_store.py             # SQLMetricsStore（MySQL/PG 生产实现）
│   │   ├── factory.py               # create_metrics_store() 工厂函数
│   │   └── prometheus.py            # Prometheus 指标导出（Counter / Histogram / Gauge）
│   ├── rag/                         # 向量检索引擎
│   │   └── qdrant.py                # QdrantSearch（混合检索、分页遍历、集合管理）
│   └── session/                     # 会话管理
│       ├── base.py                  # SessionStore 抽象基类
│       ├── data.py                  # SessionData + TurnRecord + trim_or_compress
│       ├── memory.py                # MemorySessionStore（字典存储，含 TTL 清理线程）
│       └── redis_store.py           # RedisSessionStore（生产环境共享存储）
├── tests/                           # 测试套件
│   ├── conftest.py                  # 共享 fixtures（tmp_path、mock httpx2 等）
│   ├── test_api.py                  # API 端点测试
│   ├── test_auth.py                 # 认证中间件测试
│   ├── test_builder.py              # 文档构建器测试
│   ├── test_chunker.py              # 文本分块器测试
│   ├── test_cli.py                  # CLI 工具测试
│   ├── test_config.py               # 配置加载测试
│   ├── test_coverage_edge.py        # 边界条件和覆盖测试
│   ├── test_dag_engine.py           # DAG 引擎测试
│   ├── test_db_integration.py       # 数据库集成测试
│   ├── test_db.py                   # 数据库连接池测试
│   ├── test_embed_service.py        # Embedding 服务测试
│   ├── test_gui.py                  # GUI 组件测试
│   ├── test_llm_client.py           # LLM 客户端测试
│   ├── test_metrics.py              # Metrics 存储测试
│   ├── test_qdrant.py               # Qdrant 检索测试
│   ├── test_session_store.py        # 会话存储测试
│   ├── test_tool_impl.py            # 工具实现测试
│   ├── test_tool_impl_extra.py      # 工具实现补充测试
│   └── test_tools.py                # 工具系统测试
├── deployment/k8s-aliyun/                             # Kubernetes 部署清单
│   ├── namespace.yaml               # Namespace 定义
│   ├── secret.yaml                  # Secret 模板（含占位符）
│   ├── ingress.yaml                 # ALB Ingress 配置
│   ├── kustomization.yaml           # Kustomize 编排
│   ├── oss-pvc.yaml                 # OSS CSI 持久卷声明
│   ├── job-build.yaml               # 文档构建 Job
│   ├── grafana-dashboard.json       # Grafana 监控面板
│   ├── prometheus-rules.yaml        # Prometheus 告警规则
│   ├── chat-api/                    # 用户流量 Deployment
│   ├── admin-api/                   # 管理后台 Deployment
│   ├── embed/                       # Embedding 服务 Deployment
│   └── qdrant/                      # Qdrant StatefulSet
├── deployment/scripts/                         # 运维脚本
├── docker-compose.yaml              # 本地开发编排（embed + qdrant + api）
├── Dockerfile                       # API 镜像（chat-api / admin-api 共用）
├── Dockerfile.embed                 # kf-embed 向量化服务镜像
├── pyproject.toml                   # 项目元数据与工具配置
└── Jenkinsfile                      # CI/CD 流水线
```

---

## 数据流

用户输入在系统中的完整流转路径：

```
用户输入 → POST /api/v1/workflows/{name}/run
  │
  ├─ 1. SessionStore.get_or_create(chat_id) → SessionData
  │      └─ MemorySessionStore（开发）/ RedisSessionStore（生产）
  │
  ├─ 2. DAGEngine.run(workflow_name, query, session)
  │      │
  │      ├─ 2a. 拓扑遍历（BFS + deque）
  │      │      ├─ 普通节点：顺序执行 tool_fn(node_config, session) → {text, ...}
  │      │      ├─ if-then 分支：根据前一节点输出选择后继路径
  │      │      └─ switch 并行分支：ThreadPoolExecutor 并发执行各分支
  │      │
  │      ├─ 2b. 分支汇聚（merge 工具）：将并行分支结果合并为统一输出
  │      │
  │      ├─ 2c. _finish：到达 output 节点，生成最终回复
  │      │
  │      └─ 2d. _collect_metrics：收集完整执行轨迹
  │             ├─ runs（session × turn）记录
  │             ├─ node_logs（节点输入/输出/耗时/错误）记录
  │             ├─ tool_logs（工具调用详情）记录
  │             └─ Prometheus Counter / Histogram 更新
  │
  ├─ 3. session.add_turn(query, reply) → trim_or_compress
  │      ├─ TTL 裁剪：移除超过 max_age 的旧轮次
  │      └─ 容量压缩：超出 max_turns 时，LLM 摘要旧对话
  │
  ├─ 4. SessionStore.save(session) → 持久化
  │
  └─ 5. JSONResponse { chat_id, turn_id, reply }
```

**DAG 节点间的数据传递**：
- 每个节点执行后将输出存入 `session.nodes[node_name].data`
- 下游节点可通过 `session["node_name"]` 引用上游输出
- 模板渲染引擎支持 `{{session.node_name.field}}` 变量插值

---

## 关键设计决策

### 1. YAML 驱动配置 + 环境变量插值

所有配置统一为 YAML 文件（`config/*.yaml`），支持 `${ENV_VAR}` 和 `${ENV_VAR:-default}` 插值语法。同级配置文件和父级输出是统一的文件夹结构，通过 `AppConfig` 单例在进程中共享，支持运行时 `/reload` 热重载。

### 2. 工作流隔离

每个产品线拥有独立的配置目录（`config/workflows/{name}/`），包含：
- `workflow.yaml`：DAG 拓扑定义
- `nodes/`：各节点的工具类型、参数、提示词配置
- 独立的知识库列表、API 密钥列表、路由规则

工作流之间互不干扰，天然支持多租户。

### 3. 统一工具签名

所有工具函数遵循 `fn(config: dict, session: SessionData) -> dict` 签名。`config` 为 YAML 节点配置字典，`session` 为当前会话对象（类字典接口，可通过 `session["node_name"]` 获取上游输出）。返回 `dict` 统一为 `{"text": "...", ...}` 格式。

### 4. 不做供应商 SDK 锁定

所有 LLM 调用统一经 `httpx2` REST API 发出，不依赖 openai / anthropic 等 SDK。`LLMClient` 封装底层 provider 差异（OpenAI 兼容 vs Anthropic），对外暴露统一 `chat` / `stream_chat` 接口。切换 LLM 供应商无需修改业务代码。

### 5. Embedding 独立微服务

kf-embed 作为独立容器部署（`Dockerfile.embed`），引擎为 FastEmbed/ONNX，模型为 `nomic-embed-text`（768d）。暴露 `/v1/embeddings` OpenAI 兼容接口供 kf-api 调用。独立扩缩容，不占用 LLM 推理资源。

### 6. 会话存储双模

开发环境使用 `MemorySessionStore`（字典存储 + TTL 清理线程），生产环境使用 `RedisSessionStore`（Redis 共享存储，多 Worker 一致性）。`trim_or_compress` 自动维护会话上下文在 token 窗口限制内。

### 7. 三级 Metrics 追踪体系

```
runs（对话轮次）
  └─ node_logs（节点执行详情）
       └─ tool_logs（工具调用详情）
```

支持 SQLite（开发）/ MySQL（生产）/ PostgreSQL（分析）三种存储后端，通过 `dialect.py` 适配多数据库 SQL 方言。同时暴露 Prometheus 指标供 Grafana 可视化。

### 8. 单镜像双部署

chat-api 和 admin-api 使用同一个 `Dockerfile` 构建的镜像，通过 `KF_MODE` 环境变量选择加载的路由组。减少镜像构建和维护成本，同时保证版本一致性。
