# KF 人工测试计划

> 创建时间: 2026-07-03
> 环境: Windows 11 + WSL (Qdrant Docker, Ollama systemd)
> Python: `.venv\Scripts\python.exe` (3.11.11)

---

## 环境概况

| 服务 | 位置 | 端口 | 状态 |
|------|------|------|------|
| Qdrant v1.18.2 | WSL Docker `kf-qdrant` | 6333 (REST), 6334 (gRPC) | 运行中 |
| Ollama | WSL systemd | 11434 | 运行中 |
| qwen3-8b | Ollama | - | 已拉取 |
| nomic-embed-text | Ollama | - | 已拉取 |
| FastAPI | Windows `.venv` | 9000 | 待启动 |
| Streamlit | Windows `.venv` | 8501 | 待启动 |

---

## 启动命令

**关于 API Key**: 当前 `config/auth.yaml` 中 `api_keys` 为空列表，鉴权已禁用。Layer 1-4 的所有 API 测试无需传 `X-API-Key` 头。如需测试 Layer 5.6（认证），先启用 auth：

```yaml
# config/auth.yaml — 取消注释:
api_keys:
  - "test-key-123"
```

然后在 GUI 侧边栏输入 `test-key-123`。

```powershell
# 终端 1: 启动 FastAPI
.venv\Scripts\python.exe -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 9000

# 终端 2 (可选): 启动 Streamlit GUI
.venv\Scripts\python.exe -m streamlit run src\gui\app.py --server.port 8501
```

---

## 命令规范

所有命令使用 `$WIN_IP` 变量。测试前设置：

**PowerShell**:
```powershell
$WIN_IP = "localhost"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

**WSL / Linux**:
```bash
export WIN_IP=$(ip route show default | awk '{print $3}')
# 写入 ~/.bashrc 永久生效:
# echo 'export WIN_IP=$(ip route show default | awk "{print \$3}")' >> ~/.bashrc
```

> **注意**: 不要用 `curl.exe`，它在 PowerShell 中与引号/UTF-8 不兼容。

---

## Layer 1: 基础设施健康检查

> 依赖: 无 | 目标: 验证 Qdrant / Ollama / FastAPI 启动正常

| # | 测试点 | Linux / WSL | PowerShell | 预期结果 |
|---|--------|-------------|------------|----------|
| 1.1 | Qdrant 存活 | `curl http://$WIN_IP:6333/` | `Invoke-RestMethod -Uri http://$WIN_IP:6333/` | JSON 含 `"title":"qdrant - vector search engine"` |
| 1.2 | Qdrant gRPC | `curl http://$WIN_IP:6334/` | `Invoke-RestMethod -Uri http://$WIN_IP:6334/` | 空响应或 gRPC 错误（端口存活即通过） |
| 1.3 | Ollama 模型列表 | `curl http://$WIN_IP:11434/api/tags` | `Invoke-RestMethod -Uri http://$WIN_IP:11434/api/tags` | 含 `qwen3-8b` 和 `nomic-embed-text` |
| 1.4 | FastAPI 启动 | 终端 1 执行启动命令 | — | `Uvicorn running on http://0.0.0.0:9000` |
| 1.5 | /health | `curl http://$WIN_IP:9000/health` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/health` | `{"status":"ok","timestamp":...}` |
| 1.6 | /ready | `curl http://$WIN_IP:9000/ready` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/ready` | probes 全 ok，workflows 列出 default/customer_service |
| 1.7 | /metrics | `curl http://$WIN_IP:9000/metrics` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/metrics` | Prometheus 文本，含 `kf_` 指标 |
| 1.8 | /workflows | `curl http://$WIN_IP:9000/workflows` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/workflows` | 列出 default, customer_service |
| 1.9 | /workflows/default | `curl http://$WIN_IP:9000/workflows/default` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/workflows/default` | 2 节点，含 next_type/next |
| 1.10 | /workflows/customer_service | `curl http://$WIN_IP:9000/workflows/customer_service` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/workflows/customer_service` | 5 节点，含 if-then |

---

## Layer 2: 文档入库

> 依赖: Layer 1 | 目标: 验证 CLI / API 入库全链路

### CLI 参数速查

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--dir` | `data/documents` | 源目录路径 |
| `--collection` | `default` | Qdrant 集合名 |
| `--chunk-size` | `800` | 分块字符数 |
| `--chunk-overlap` | `128` | 块间重叠字符数 |
| `--extensions` | (空) | 空=自动检测全部格式，指定则仅处理指定格式 |

### 支持的文档格式

| 格式 | 扩展名 | 依赖 |
|------|--------|------|
| 纯文本 | `.txt` | 无 |
| Markdown | `.md` | 无 |
| PDF | `.pdf` | `pymupdf` |
| Word | `.docx` | `python-docx` |
| Excel | `.xlsx` | `openpyxl` |
| CSV | `.csv` | 无 |
| HTML | `.html` `.htm` | 无 |

### 准备测试数据

```powershell
New-Item -ItemType Directory -Force -Path "data\documents"
```

创建以下 4 个文件到 `data\documents\`：

**产品介绍.md**:
```markdown
# 智能客服系统介绍
## 产品概述
智能客服系统是一套基于大模型的自动化客服解决方案，支持多渠道接入、意图识别、知识库检索、多轮对话。

## 核心功能
### 1. 多渠道接入
支持网站、APP、微信、钉钉等渠道的消息接入，统一处理逻辑。
### 2. 意图识别
基于大模型自动识别用户意图，准确率可达95%以上。
### 3. 知识库管理
支持文档上传、自动分块、向量化存储，检索速度 < 100ms。
### 4. 多轮对话
支持上下文记忆，可维护长达 100 轮的对话历史。

## 部署方式
- 公有云 SaaS
- 私有化部署
- 混合云部署

## 技术架构
采用 FastAPI + Qdrant + Ollama 技术栈，支持水平扩展。
```

**价格说明.txt**:
```
智能客服系统价格说明

标准版：￥9,800/年
- 支持 3 个坐席
- 10 万条知识库容量
- 基础意图识别

专业版：￥29,800/年
- 支持 10 个坐席
- 50 万条知识库容量
- 高级意图识别 + 情绪分析

企业版：￥98,000/年
- 坐席数不限
- 知识库容量不限
- 全部高级功能 + 私有化部署
```

**FAQ.csv**:
```
问题,回答
如何修改密码,登录后在"个人中心"->"安全设置"中修改密码，需要验证原密码。
系统支持哪些浏览器,推荐使用 Chrome、Edge、Firefox 最新版本。
退款政策是什么,购买后7天内可无条件退款，超过7天按使用时长计算。
```

**服务协议.html**:
```html
<html><body>
<h1>智能客服系统服务协议</h1>
<p>本协议是用户与智能客服系统之间关于使用服务所订立的协议。</p>
<h2>1. 服务内容</h2>
<p>智能客服系统向用户提供在线客服、知识库管理、数据分析等服务。</p>
<h2>2. 用户义务</h2>
<p>用户不得利用本系统从事违法违规活动，不得上传病毒或恶意代码。</p>
</body></html>
```

### 测试用例

| # | 测试点 | Linux / WSL | PowerShell | 预期结果 |
|---|--------|-------------|------------|----------|
| 2.1 | CLI 自动检测所有格式 | `.venv\Scripts\python.exe -m src.cli.build --collection l2_auto --dir data/documents` | 同左 | 打印 `Extensions: (...)`，chunk 数 N > 0 |
| 2.2 | CLI 指定格式 | `.venv\Scripts\python.exe -m src.cli.build --collection l2_mdonly --extensions .md` | 同左 | 只处理 .md，chunk 数少于 2.1 |
| 2.3 | CLI 自定义分块 | `.venv\Scripts\python.exe -m src.cli.build --collection l2_small --chunk-size 256 --chunk-overlap 32` | 同左 | chunk 数比默认(800)更多 |
| 2.4 | CLI 目录不存在 | `.venv\Scripts\python.exe -m src.cli.build --dir data/no_dir` | 同左 | `NotADirectoryError` |
| 2.5 | API 目录扫描 | `curl -X POST -F "directory=data/documents" -F "collection=l2_api" http://$WIN_IP:9000/documents/scan` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/documents/scan -Method Post -Body @{directory="data/documents";collection="l2_api"}` | `{"status":"ok","chunks":N}` |
| 2.6 | API 上传 Markdown | `curl -X POST -F "file=@data/documents/产品介绍.md" -F "collection=l2_upload" http://$WIN_IP:9000/documents/upload` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/documents/upload -Method Post -Form @{file=Get-Item "data\documents\产品介绍.md";collection="l2_upload"}` | `{"status":"ok","file":"产品介绍.md","chunks":N}` |
| 2.7 | API 上传 CSV | `curl -X POST -F "file=@data/documents/FAQ.csv" -F "collection=l2_upload" http://$WIN_IP:9000/documents/upload` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/documents/upload -Method Post -Form @{file=Get-Item "data\documents\FAQ.csv";collection="l2_upload"}` | `{"status":"ok","file":"FAQ.csv","chunks":N}` |
| 2.8 | API 上传 HTML | `curl -X POST -F "file=@data/documents/服务协议.html" -F "collection=l2_upload" http://$WIN_IP:9000/documents/upload` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/documents/upload -Method Post -Form @{file=Get-Item "data\documents\服务协议.html";collection="l2_upload"}` | `{"status":"ok","file":"服务协议.html","chunks":N}` |
| 2.9 | 幂等性验证 | 重复执行 2.5 | 同左 | chunk 数与第一次一致 |
| 2.10 | 扫描不存在的目录 | `curl -X POST -F "directory=data/nope" -F "collection=x" http://$WIN_IP:9000/documents/scan` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/documents/scan -Method Post -Body @{directory="data/nope";collection="x"}` | 400, directory not found |

---

## Layer 2.5: 知识库管理

> 依赖: Layer 2 | 目标: 验证 CLI + API 增删改查

### CLI 管理命令

| 命令 | 说明 |
|------|------|
| `python -m src.cli.manage list` | 列出所有集合 |
| `python -m src.cli.manage info <name>` | 集合详情 |
| `python -m src.cli.manage count <name>` | 文档总数 |
| `python -m src.cli.manage browse <name> --limit N` | 分页浏览 |
| `python -m src.cli.manage search <name> "关键词"` | 语义检索 |
| `python -m src.cli.manage delete <name>` | 删除集合 |

### 测试用例

| # | 测试点 | Linux / WSL | PowerShell | 预期结果 |
|---|--------|-------------|------------|----------|
| 2.5.1 | CLI 列出集合 | `.venv\Scripts\python.exe -m src.cli.manage list` | 同左 | 至少 l2_auto, l2_api, l2_upload |
| 2.5.2 | CLI 集合详情 | `.venv\Scripts\python.exe -m src.cli.manage info l2_auto` | 同左 | points_count > 0, config |
| 2.5.3 | CLI 计数 | `.venv\Scripts\python.exe -m src.cli.manage count l2_auto` | 同左 | `l2_auto: N points` |
| 2.5.4 | CLI 浏览 | `.venv\Scripts\python.exe -m src.cli.manage browse l2_auto --limit 5` | 同左 | 5 个点，含 id/source/text |
| 2.5.5 | CLI 语义搜索 | `.venv\Scripts\python.exe -m src.cli.manage search l2_auto "多渠道接入" --limit 3` | 同左 | 3 条结果，score 降序 |
| 2.5.6 | CLI 删除确认 | `.venv\Scripts\python.exe -m src.cli.manage delete l2_small` | 同左 | 提示确认后删除 |
| 2.5.7 | CLI 跳过确认 | `.venv\Scripts\python.exe -m src.cli.manage delete l2_mdonly --yes` | 同左 | 直接删除，不提示 |
| 2.5.8 | API 列出集合 | `curl http://$WIN_IP:9000/collections` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/collections` | `{"collections":[...]}` |
| 2.5.9 | API 集合详情 | `curl http://$WIN_IP:9000/collections/l2_auto` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/collections/l2_auto` | points_count > 0, config |
| 2.5.10 | API 计数 | `curl http://$WIN_IP:9000/collections/l2_auto/count` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/collections/l2_auto/count` | `{"collection":"l2_auto","count":N}` |
| 2.5.11 | API 浏览 | `curl "http://$WIN_IP:9000/collections/l2_auto/browse?limit=3"` | `Invoke-RestMethod -Uri "http://$WIN_IP:9000/collections/l2_auto/browse?limit=3"` | 3 个点 + next_offset |
| 2.5.12 | API 删不存在的集合 | `curl -X DELETE http://$WIN_IP:9000/collections/no_such` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/collections/no_such -Method Delete` | 404 |
| 2.5.13 | API 删除集合 | `curl -X DELETE http://$WIN_IP:9000/collections/l2_upload` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/collections/l2_upload -Method Delete` | `{"status":"deleted","collection":"l2_upload"}` |

---

## Layer 3: 单节点工作流

> 依赖: Layer 2 | 目标: 验证 default 工作流 (retrieve → generate)

| # | 测试点 | Linux / WSL | PowerShell | 预期结果 |
|---|--------|-------------|------------|----------|
| 3.1 | 首次对话 | `curl -X POST -H "Content-Type: application/json" -d '{"query":"你好"}' http://$WIN_IP:9000/workflows/default/run` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/workflows/default/run -Method Post -ContentType "application/json; charset=utf-8" -Body '{"query":"你好"}'` | chat_id, turn_id=1, reply 非空 |
| 3.2 | 知识库命中 | `curl -X POST -H "Content-Type: application/json" -d '{"query":"你们系统支持哪些渠道接入"}' http://$WIN_IP:9000/workflows/default/run` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/workflows/default/run -Method Post -ContentType "application/json; charset=utf-8" -Body '{"query":"你们系统支持哪些渠道接入"}'` | reply 含"网站""APP""微信" |
| 3.3 | 知识库未命中 | `curl -X POST -H "Content-Type: application/json" -d '{"query":"Python 4.0 什么时候发布"}' http://$WIN_IP:9000/workflows/default/run` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/workflows/default/run -Method Post -ContentType "application/json; charset=utf-8" -Body '{"query":"Python 4.0 什么时候发布"}'` | reply 友好告知未找到 |
| 3.4 | 多轮续接 | 用 3.1 的 chat_id 替换 `<id>`：`curl ... -d '{"query":"刚才提到了什么","chat_id":"<id>"}' http://$WIN_IP:9000/workflows/default/run` | `Invoke-RestMethod ... -Body '{"query":"刚才提到了什么","chat_id":"<id>"}'` | reply 引用前文，turn_id 递增 |
| 3.5 | 空 query | `curl -X POST ... -d '{"query":""}' http://$WIN_IP:9000/workflows/default/run` | `Invoke-RestMethod ... -Body '{"query":""}'` | 422 |
| 3.6 | 不存在的 workflow | `curl -X POST ... -d '{"query":"test"}' http://$WIN_IP:9000/workflows/fake/run` | `Invoke-RestMethod ... -Body '{"query":"test"}'` | 404 |
| 3.7 | 跨 workflow chat_id | 用 default 的 chat_id 请求 customer_service | 同上 | 400, 提示 session 属于 default |
| 3.8 | 不存在的 chat_id | `curl -X POST ... -d '{"query":"test","chat_id":"deadbeef"}' http://$WIN_IP:9000/workflows/default/run` | `Invoke-RestMethod ... -Body '{"query":"test","chat_id":"deadbeef"}'` | 404 |

---

## Layer 4: 多节点工作流 (customer_service)

> 依赖: Layer 3 | 目标: 验证 if-then 路由分发 + 多分支 + merge

| # | 测试点 | Linux / WSL | PowerShell | 预期结果 |
|---|--------|-------------|------------|----------|
| 4.1 | 问候路由 | `curl -X POST -H "Content-Type: application/json" -d '{"query":"你好"}' http://$WIN_IP:9000/workflows/customer_service/run` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/workflows/customer_service/run -Method Post -ContentType "application/json; charset=utf-8" -Body '{"query":"你好"}'` | inquiry_handler → final_merge |
| 4.2 | 投诉路由 | `curl -X POST -H "Content-Type: application/json" -d '{"query":"我要投诉产品质量太差了"}' http://$WIN_IP:9000/workflows/customer_service/run` | `Invoke-RestMethod ... -Body '{"query":"我要投诉产品质量太差了"}'` | complaint_handler → final_merge |
| 4.3 | 订单路由 | `curl -X POST -H "Content-Type: application/json" -d '{"query":"我的订单什么时候发货"}' http://$WIN_IP:9000/workflows/customer_service/run` | `Invoke-RestMethod ... -Body '{"query":"我的订单什么时候发货"}'` | order_handler → final_merge |
| 4.4 | 退款路由 | `curl -X POST -H "Content-Type: application/json" -d '{"query":"我要退款"}' http://$WIN_IP:9000/workflows/customer_service/run` | `Invoke-RestMethod ... -Body '{"query":"我要退款"}'` | complaint_handler → final_merge |
| 4.5 | 默认分支 | `curl -X POST -H "Content-Type: application/json" -d '{"query":"今天天气怎么样"}' http://$WIN_IP:9000/workflows/customer_service/run` | `Invoke-RestMethod ... -Body '{"query":"今天天气怎么样"}'` | default: inquiry_handler |
| 4.6 | 确定性验证 | 同一 query 执行 2 次 | 同左 | 两次路由结果一致 |

---

## Layer 5: 完整体验

> 依赖: Layer 4 | 目标: GUI、会话管理、认证、指标

| # | 测试点 | Linux / WSL | PowerShell | 预期结果 |
|---|--------|-------------|------------|----------|
| 5.1 | Streamlit 启动 | 终端 2 执行启动命令 | 同左 | http://localhost:8501 可访问 |
| 5.2 | GUI 侧边栏状态 | 打开页面 | — | 连接 OK，Auth Disabled |
| 5.3 | GUI 单轮对话 | 输入 "你好"，default workflow | — | 消息 + 时间戳显示 |
| 5.4 | GUI 多轮对话 | 连续 3 条消息 | — | 回复含上下文 |
| 5.5 | GUI 错误重试 | 停止 FastAPI → 在 GUI 发消息 → 看到"连接失败" → 重启 FastAPI → 再发一条消息 | — | 新消息正常返回（无 Retry 按钮，直接再发即可） |
| 5.6 | GUI 输入 API Key | 先在 `config/auth.yaml` 启用 auth（取消注释 key 或设置 `KF_API_KEY` 环境变量并取消注释），然后在侧边栏输入相同 key | — | 侧边栏显示"已认证 - 已连接" |
| 5.7 | DELETE session | `curl -X DELETE http://$WIN_IP:9000/sessions/<chat_id>` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/sessions/<chat_id> -Method Delete` | 204 |
| 5.8 | DELETE 不存在 | `curl -X DELETE http://$WIN_IP:9000/sessions/fake` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/sessions/fake -Method Delete` | 404 |
| 5.9 | /metrics 更新 | `curl http://$WIN_IP:9000/metrics` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/metrics` | `kf_llm_calls_total` 递增 |
| 5.10 | 认证关闭 | 不传 X-API-Key | — | 正常通过 |
| 5.11 | /sessions 会话列表 | `curl http://$WIN_IP:9000/sessions` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/sessions` | `{"sessions":[...]}` 含 chat_id, turn_count, duration |
| 5.12 | /sessions/{id} 轮次列表 | 用 5.11 拿到的 chat_id：`curl http://$WIN_IP:9000/sessions/<id>` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/sessions/<id>` | `{"chat_id":"...","turns":[...]}` 含 query/reply/duration |
| 5.13 | /sessions/{id}/turns/{n} 节点列表 | `curl http://$WIN_IP:9000/sessions/<id>/turns/0` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/sessions/<id>/turns/0` | 含 run 详情 + nodes 列表 |
| 5.14 | /sessions/{id}/turns/{n}/nodes/{name} 工具调用 | `curl http://$WIN_IP:9000/sessions/<id>/turns/0/nodes/retrieve` | `Invoke-RestMethod -Uri http://$WIN_IP:9000/sessions/<id>/turns/0/nodes/retrieve` | 含 node 详情 + tools 列表 (入参/返回/耗时) |

---

## 反馈模板

```
Layer: X
测试号: X.X
结果: [PASS / FAIL]
现象: <简短描述>
```
