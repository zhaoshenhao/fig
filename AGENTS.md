# AGENTS.md — 项目决策记录

## 🚨 最高优先级安全规则（必须始终遵守）

**禁止在任何提交到源代码仓库的文件中包含敏感信息。**

**🚨 Git 操作必须经用户同意**: 任何 `git add`、`git commit`、`git push` 操作执行前，必须获得用户明确同意。禁止自动提交和推送。 包括但不限于：
- 密码、passwords、passwd
- AccessKey、SecretKey、AK/SK、Access Key ID/Secret
- API Key、Token、Bearer Token
- 连接字符串中的用户名和密码（如 `mysql://user:pass@host`）
- 数据库账号密码、Redis 密码
- 任何形式的私钥、证书

**所有敏感信息只能通过以下方式注入：**
- 环境变量（`.env` 文件已在 `.gitignore` 中排除）
- Kubernetes Secret（模板文件中使用占位符 `<PLACEHOLDER>`，真实值不提交）
- CI/CD 凭据管理系统（如 Jenkins Credentials）
- `Jenkinsfile` 中必须使用 `withCredentials` 引用凭据 ID，**严禁**直接在文件中写密码

**后果：一旦推送到 GitHub/Gitea，即视为凭证泄露，必须立即轮换。**

---

## 项目概述
多产品线智能客服（智能客服）系统。Python >=3.12，FastAPI + Vue SPA + Qdrant。

## 技术栈决策

### 运行时
- Python 3.14.5
- 所有 PyPI 依赖取最新稳定版

### 核心依赖
| 包 | 用途 |
|-----|------|
| fastapi | API 框架（自带 pydantic, uvicorn） |
| qdrant-client | 向量库客户端，prefer_grpc=True |
| httpx2 | HTTP 客户端，LLM + Embeddings 调用（DeepSeek + kf-embed） |
| pyyaml | 配置文件解析 |
| python-multipart | 文件上传 |

### API 拆分
- **chat-api**: 用户流量，`KF_MODE=chat`，暴露 `/api/v1/workflows/*/run`, `/api/v1/sessions/*`
- **admin-api**: 内部管理，`KF_MODE=admin`，暴露 `/metrics/*`, `/collections/*`, `/documents/*`
- 同一 Docker 镜像，通过 `KF_MODE` 环境变量选择加载的路由组
- 共享代码在 `src/api/state.py`（单例 getter/setter），路由在 `src/api/routes_chat.py` / `routes_admin.py` |

### 禁止项
- 禁止使用 openai/anthropic 等 LLM 供应商 SDK → 统一 httpx2 REST API
- 禁止使用 sentence-transformers → Embeddings 走 kf-embed 微服务（FastEmbed/ONNX）
- 禁止使用 watchfiles → 文件监控用轮询或手动触发
- 新增依赖必须手动确认（已确认：fastembed 用于 kf-embed 微服务，见 optional-deps `embed`）

### Embedding（kf-embed 微服务）
- 部署：独立容器（`Dockerfile.embed`），CPU 即可运行，1 副本
- 引擎：FastEmbed（Qdrant 官方 ONNX 推理库），非 Ollama
- 嵌入模型：`nomic-embed-text`（768d，FastEmbed 名 `nomic-ai/nomic-embed-text-v1.5`）
- Embedding API：`{EMBED_BASE_URL}/v1/embeddings`，OpenAI 兼容格式（端口 8100）
- 就绪探针 `/ready`：模型加载完成才返回 200（模型已烘焙进镜像，仅需加载入内存，数秒）
- 模型构建期预下载（`Dockerfile.embed` RUN 阶段，`FASTEMBED_CACHE_PATH=/opt/fastembed_cache`），运行期不联网
- 零费用、零外网依赖、低延迟
- Rerank：改用 Qdrant RRF
- LLM 不走本地：统一走外部 DeepSeek API

### Qdrant
- 独立 Docker 服务，不嵌入应用
- 始终 gRPC（prefer_grpc=True）
- 开发：localhost:6334
- 生产：ACK StatefulSet 3副本 + ESSD 云盘
- 允许读写（非只读部署）
- 多 Worker 共享同一 Qdrant DB（SQLite WAL 支持并发读）
- 混合检索：Dense Vector (768d) + Sparse BM25，RRF 分数融合，不设独立 reranker

### 工作流引擎
- DAG 驱动（depends_on 字段）
- 每个产品线一个独立 workflow，独立 context_path 和 API key 列表
- 配置：workflow.yaml + 节点 yaml 目录
- 工具系统：llm, rag_search, db_query, api_call, web_search, code, router, merge

### 文档构建
- API 上传 + 目录扫描（均手动触发）
- 独立构建脚本，与应用分离

### Streamlit GUI
- 已被 Vue 3 + Vite SPA 取代
- SPA 静态文件托管于阿里云 OSS（`kf-ui-{env}` bucket），CDN 分发
- 开发模式用 Vite 代理 `/api/v1` → 本地 FastAPI（端口 9000）
- **不**再与 kf-api 同进程部署，从 Dockerfile 中完全移除

### LLM 多供应商
- 通过 httpx2 REST API 直连各供应商
- API key 配置在 workflow 级 auth.yaml（固定 key 列表）

### 测试
- mock httpx2.Client（unittest.mock）
- tmp_path fixture 模拟 Qdrant 环境
- mock 工具函数测 workflow engine
- 不用 pytest-httpx（不兼容 httpx2）

### 生产部署
- ACK 托管版 K8s（阿里云容器服务）
- 已有现有 ACK 集群
- ALB Ingress（`/api` 流量 → chat-api/admin-api 双 backend，SPA 走 OSS/CDN）
- 3 个容器镜像：kf-api（FastAPI）、kf-embed（FastEmbed 向量化）、Qdrant
- kf-api: 2 个 Deployment（chat-api + admin-api），同一镜像，通过 `KF_MODE` 环境变量区分路由组
- kf-embed: Deployment 1副本（模型烘焙进镜像，无需 PVC）
- Qdrant: StatefulSet 1副本 + ESSD 云盘（测试环境无冗余）
- 外部托管：Redis（会话共享）、MySQL RDS（metrics/主库）、PostgreSQL RDS（分析）、DeepSeek API（LLM）
- config 烘焙进镜像，环境值经 env + Secret 覆盖（无 ConfigMap 工作流挂载）
- 工作流 YAML 配置通过 OSS CSI PVC 挂载到 `/app/config/workflows`
- 已移除：Ollama、Streamlit（Streamlit 被 Vue SPA 取代）
- 部署清单见 `deployment/k8s-aliyun/`，Jenkins 流水线 `Jenkinsfile`，指南见 `docs/deployments/deployment_CN.md`

### 数据库迁移规范
- Schema 唯一定义在 `src/metrics/schema.py`（canonical source of truth）
- 版本化迁移在 `src/metrics/migration.py`（`Migration` 数据类 + `MIGRATIONS` 列表）
- 启动时自动执行 `migrate(conn, dialect)`，检测 schema 漂移并备份旧表
- 新增迁移步骤见 `docs/deployments/db-schema-norm.md`
- 版本号递增，已执行的迁移自动跳过

## 操作规范（重要）
- **所有服务进程必须后台非阻塞启动**，绝不阻塞自身，保持随时可响应用户、可检查后台进程
- 用 `Start-Process ... -PassThru`（立即返回 Id），**禁止** `Start-Sleep` 等待启动
- 就绪检测用单次快速轮询（`netstat -ano | findstr ":PORT"` 或短超时请求），未就绪则报告后继续，不干等
- PowerShell 5.1 的 `Invoke-WebRequest` 必须加 `-UseBasicParsing`（否则 200 响应触发 IE 解析器 NonInteractive 报错）；无 `-SkipHttpErrorCheck`（PS7+ 才有），取状态码用 try/catch 读 `$_.Exception.Response`
- 服务启动日志重定向到 `$env:TEMP\*.log`，需要时读取

## 本地开发启动

| 操作 | 命令 |
|------|------|
| 一键启动全部 | `.\scripts\dev\start-all.ps1` |
| 仅 Qdrant | `.\scripts\dev\start-qdrant.ps1` |
| 仅 kf-embed | `.\scripts\dev\start-embed.ps1` |
| 仅 kf-api | `.\scripts\dev\start-api.ps1` |
| 数据库初始化 | `.\scripts\dev\init-db.ps1` |

服务端口：Qdrant :6333/:6334 (WSL Docker)，kf-embed :8100，kf-api :9000，MySQL :3307 (WSL Docker)

## 文档索引
- 根目录 `README.md`（中文） / `README_EN.md`（英文）
- `docs/architecture_CN.md` — 系统架构、模块关系、目录结构
- `docs/reference/api-reference_CN.md` — 完整 HTTP API 参考
- `docs/design/workflow_CN.md` — 工作流设计与配置指南
- `docs/design/session_CN.md` — 会话管理与存储后端
- `docs/design/metrics_CN.md` — 指标系统与执行追踪
- `docs/reference/tools-reference_CN.md` — 内置工具 + CLI + 工具开发指南
- `docs/database/database_CN.md` — 数据库连接池 + Schema 迁移规范
- `docs/test/testing_CN.md` — 测试结构与运行方法
- `docs/deployments/local-setup_CN.md` — 本地开发环境搭建
- `docs/deployments/deployment_CN.md` — K8s 部署 (ACK + AWS EKS)
- `docs/test/manual-test_CN.md` — 手工测试计划
- 每个文档有对应英文版 `*_EN.md`，通过顶部链接切换

### K8s Secret 管理
- 所有凭据存储在 `kf-secrets` Secret（namespace=mb-test/mb-pr）
- `deployment/k8s-aliyun/secret.yaml` 是模板，含占位符，**不提交真实密钥**
- 三种创建方式：脚本 `deployment/scripts/create-k8s-secrets.sh`、kubectl `--from-literal`、Jenkins `withCredentials`
- Deployments 通过 `envFrom.secretRef` 或 `valueFrom.secretKeyRef` 引用
- 凭据清单: DEEPSEEK_API_KEY, KF_API_KEY, EMBED_API_KEY, REDIS_URL, MYSQL_*, PG_*, OSS_AK_*
- 未来可迁移到阿里云 KMS（ack-kms-secret 插件 → ExternalSecret CRD）
