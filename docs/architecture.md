# 源代码目录结构

```
kf/
├── config/                         # ─── 配置文件目录 ───
│   ├── .env.example                #     环境变量模板
│   ├── auth.yaml                   #     API 密钥 + 跳过路径
│   ├── db.yaml                     #     数据库连接池配置
│   ├── embed.yaml                  #     Embedding 供应商 (Ollama/OpenAI)
│   ├── llm.yaml                    #     LLM 供应商 (Ollama/OpenAI/Anthropic)
│   ├── logging.yaml                #     日志级别配置
│   ├── session.yaml                #     会话管理 (TTL/ 压缩 / 清理)
│   └── workflows/                  #     工作流定义
│       ├── default/                #         默认工作流
│       │   ├── workflow.yaml       #             DAG 拓扑
│       │   └── nodes/              #             节点配置
│       │       ├── retrieve.yaml
│       │       └── generate.yaml
│       └── customer_service/       #         客服工作流
│           ├── workflow.yaml
│           └── nodes/              #             intent_classify, inquiry_handler ...
│
├── src/                            # ─── 源代码 ───
│   ├── api/                        #     FastAPI 应用
│   │   ├── __init__.py
│   │   ├── main.py                 #         路由 (workflows/sessions/documents/collections/metrics)
│   │   └── auth.py                 #         AuthMiddleware (X-API-Key)
│   │
│   ├── cli/                        #     CLI 工具
│   │   ├── __init__.py
│   │   ├── build.py                #         文档构建 CLI (ingestion)
│   │   ├── manage.py               #         知识库管理 CLI (list/info/delete/browse/search)
│   │   └── validate_workflow.py    #         工作流校验 CLI
│   │
│   ├── config.py                   #    配置加载器 (AppConfig 单例)
│   │
│   ├── db/                         #    数据库连接池
│   │   ├── __init__.py             #         工厂函数 (create_pool/get_db_pool/close_all)
│   │   ├── base.py                 #         DBConfig/DBPoolConfig/DBPool ABC
│   │   ├── mysql_pool.py           #         MySQLPool (pymysql)
│   │   └── pg_pool.py              #         PgPool (psycopg2)
│   │
│   ├── engine/                     #    DAG 工作流引擎
│   │   ├── __init__.py             #        导出 DAGEngine, ToolRegistry
│   │   ├── tool.py                 #        ToolRegistry (注册 / 获取 / 遍历)
│   │   ├── dag.py                  #        DAGEngine (拓扑遍历 / 并行分支 / 指标采集)
│   │   └── tools/                  #        内置工具
│   │       ├── __init__.py         #            延迟导入包装器
│   │       ├── llm_tool.py         #            LLM 调用
│   │       ├── rag_search.py       #            向量库检索
│   │       ├── router.py           #            条件路由
│   │       ├── merge.py            #            并行分支合并
│   │       ├── db_query.py         #            数据库查询
│   │       ├── extract_llm.py      #            LLM 信息提取
│   │       ├── extract_regex.py    #            正则提取
│   │       ├── api_call.py         #            外部 API 调用
│   │       ├── web_search.py       #            网页搜索 (DuckDuckGo)
│   │       └── code_exec.py        #            安全代码执行
│   │
│   ├── gui/                        #    Streamlit 前端
│   │   ├── __init__.py
│   │   ├── app.py                  #         5 页签 GUI (聊天 / 知识库 / 工作流 / 文档 / 指标)
│   │   └── utils.py                #         纯函数工具 (DAG 拓扑 / 文本高亮 / JSON 解析)
│   │
│   ├── ingestion/                  #    文档入库
│   │   ├── __init__.py
│   │   ├── chunker.py              #         文本分块 (段落合并 / 重叠)
│   │   └── builder.py              #         文档构建 (Embed + Upsert)
│   │
│   ├── llm/                        #    LLM 客户端
│   │   ├── __init__.py
│   │   └── client.py               #        统一 REST API 客户端 (chat/embed)
│   │
│   ├── logger/                     #    结构化日志
│   │   ├── __init__.py             #         JSONFormatter / init_logging / get_logger
│   │   └── middleware.py           #         RequestIDMiddleware (ContextVar)
│   │
│   ├── metrics/                    #    观测指标
│   │   ├── __init__.py             #         导出 MetricsStore
│   │   ├── store.py                #         SQLite 持久化 (node_logs 表)
│   │   └── prometheus.py           #         零依赖 Prometheus Counter/Histogram/Registry
│   │
│   ├── rag/                        #    向量检索 (Qdrant)
│   │   ├── __init__.py
│   │   └── qdrant.py               #         QdrantSearch (混合检索 / scroll / count)
│   │
│   └── session/                    #    会话管理
│       ├── __init__.py             #         工厂 create_session_store()
│       ├── base.py                 #         SessionStore ABC
│       ├── data.py                 #         SessionData / TurnRecord (数据类)
│       ├── memory.py               #         MemorySessionStore (内存 + TTL + 清理)
│       └── redis_store.py          #         RedisSessionStore (SETEX + JSON)
│
├── tests/                          # ─── 测试 ───
│   ├── conftest.py                 #    共享 fixture (temp_config_dir/mock_tools)
│   ├── test_auth.py                #    认证中间件 (7 tests)
│   ├── test_builder.py             #    入库构建 (31 tests)
│   ├── test_chunker.py             #    文本分块 (10 tests)
│   ├── test_cli.py                 #    CLI 校验 (25 tests)
│   ├── test_config.py              #    配置加载 (20 tests)
│   ├── test_coverage_edge.py       #    覆盖边界 (67 tests)
│   ├── test_dag_engine.py          #    DAG 引擎 (38 tests)
│   ├── test_db.py                  #    数据库连接池 (22 tests)
│   ├── test_metrics.py             #    指标采集 (14 tests)
│   ├── test_session_store.py       #    会话存储 (32 tests)
│   ├── test_tool_impl.py           #    工具实现 (24 tests)
│   ├── test_tool_impl_extra.py     #    扩展工具 (14 tests)
│   └── test_tools.py              #    工具注册 (12 tests)
│
├── k8s/                            # ─── Kubernetes 部署清单 ───
│   ├── kustomization.yaml          #    Kustomize 入口
│   ├── namespace.yaml              #    命名空间
│   ├── configmap.yaml              #    配置 (kf-config + workflow-config)
│   ├── secret.yaml                 #    认证密钥
│   ├── prometheus-rules.yaml       #    Prometheus 告警规则
│   ├── ingress.yaml                #    ALB Ingress
│   ├── job-build.yaml              #    文档构建 Job
│   ├── api/                        #    API Deployment/Service/HPA
│   ├── ollama/                     #    Ollama Deployment/Service
│   ├── qdrant/                     #    Qdrant StatefulSet/Service
│   └── streamlit/                  #    Streamlit Deployment/Service
│
├── docs/                           # ─── 文档 ───
│   ├── architecture.md             #    本文档
│   ├── cli-reference.md            #    CLI 参考手册
│   ├── tools-reference.md          #    工具参考
│   ├── tool-dev-guide.md           #    工具开发指南
│   ├── metrics.md                  #    指标数据库结构
│   ├── session-design.md           #    会话架构设计
│   ├── session-guide.md            #    会话开发指南
│   ├── workflow-design.md          #    工作流设计
│   ├── workflow-guide.md           #    工作流开发指南
│   ├── db-config.md                #    数据库配置说明
│   ├── local-setup.md              #    本地开发环境搭建
│   └── deployment/                 #    部署文档
│
├── docker-compose.yaml             # 本地一键启动
├── Dockerfile                      # API 镜像
├── Dockerfile.streamlit            # Streamlit 镜像
├── pyproject.toml                  # 项目元数据 (ruff/coverage/pytest 配置)
├── requirements.txt                # 锁定依赖
└── AGENTS.md                       # 项目决策记录
```

## 核心架构分层

```
┌─────────────────────────────────────────────┐
│                  Streamlit GUI               │  ← 前端 (只读浏览 + 聊天)
├─────────────────────────────────────────────┤
│                  FastAPI (API)               │  ← HTTP 网关 (workflows/sessions/documents/collections/metrics)
│  ┌──────────┬──────────┬──────────────────┐ │
│  │   Auth   │  Logger  │     Metrics      │ │  ← 横切中间件
│  └──────────┴──────────┴──────────────────┘ │
│  ┌────────────────────────────────────────┐  │
│  │  JSON (sync)  │  SSE streaming        │  │  ← 双模式响应 (?stream=true)
│  └────────────────────────────────────────┘  │
├─────────────────────────────────────────────┤
│                DAG Engine                    │  ← 工作流引擎 (拓扑遍历 + 并行)
│  ┌──────────────────────────────────────┐   │
│  │  llm │ rag │ router │ merge │ ...    │   │  ← 10 个内置工具
│  └──────────────────────────────────────┘   │
├──────────┬──────────┬───────────────────────┤
│ Session  │   LLM    │       Qdrant RAG      │  ← 领域服务
│ (内存 /   │ (Ollama/ │   (向量库 + BM25)      │
│  Redis)   │ 多供应商) │                         │
├──────────┴──────────┴───────────────────────┤
│               DB Pools (MySQL / PG)          │  ← 数据层
├─────────────────────────────────────────────┤
│  Qdrant  │  Ollama  │  MySQL  │ PostgreSQL  │  ← 外部依赖 (Docker)
└─────────────────────────────────────────────┘
```

## 数据流

```
用户输入 → /workflows/{name}/run
                │
                ▼
         DAGEngine.run()
                │
    ┌───────────┼───────────┐
    ▼           ▼           ▼
  节点1 → 节点2 → 节点3 → ...
    │           │           │
    └─── 工具函数 (config, session) ──→ 返回 {text, ...}
                │
                ▼
         SessionData (历史 / 数据 / 节点日志)
                │
                ▼
         MetricsStore (SQLite) + Prometheus 指标
                │
                ▼
          {chat_id, turn_id, reply}

流式模式 (?stream=true)：

```
用户输入 → /workflows/{name}/run?stream=true
                 │
                 ▼
          DAGEngine.run()  background thread
          └── llm_tool → LLMClient.stream_chat()
                 │
                 ▼
          queue.Queue ──→ asyncio.to_thread
                 │              │
                 ▼              ▼
          SSE text/event-stream  →  逐 token 推送
                 │
                 ▼
          {event: "done", chat_id, turn_id, reply}
```
```
