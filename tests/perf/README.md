# KF API 性能测试

基于知识库生成的 200 个测试问题，对 KF API 进行多轮对话压力测试。

## 文件结构

```
tests/perf/
├── README.md        # 本文件
├── questions.json   # 测试问题集 (20 sessions × 10 questions = 200 题)
└── perf_test.py     # 性能测试脚本
```

## questions.json 内容覆盖

| Session | Topic | 范围 |
|---------|-------|------|
| 1-4 | 太阳膜基础 | 定义、光谱、四大功能、六代工艺、分层结构、五维验膜 |
| 5-8 | 窗膜产品线 | WG / WR / WA / WT / 6S 五大系列参数与卖点 |
| 9-11 | 车衣基础 | 漆面养护史、材质演变 (PVC→TPU)、TPU 解析、辅材、行业参数 |
| 12-14 | 车衣产品线 | E7 / EM7 / T9 / G7 / R8 / GM7 / GH7 全系列 + 推荐策略 |
| 15-16 | 质保风控 | 质保范围、免责条款、养护规范、合规红线 |
| 17-18 | 深度对比 | 跨产品对比、场景推荐、技术参数深度问答 |
| 19-20 | 销售模拟 | 客户常见异议处理、话术演练 |

数据结构：
```json
[
  {
    "session_id": 1,
    "workflow": "auto_film",
    "topic": "太阳膜基础知识",
    "questions": ["问题1", "问题2", ...]
  },
  ...
]
```

- 同一 session 内第 1 问不带 `chat_id`（创建新会话），第 2-10 问带返回的 `chat_id`（多轮续接），模拟真实多轮对话场景
- 所有问题基于 `D:\AI\Hermes\auto-film-training\汽车膜培训视频资料整理` 知识库生成

## 脚本用法

```powershell
# 基本用法（本地开发，auth.yaml skip_paths 未覆盖 /api/v1/*，如未配置 API key 则 auth 禁用时可裸调）
python tests/perf/perf_test.py -q tests/perf/questions.json

# 生产环境（指定 API Key + 远程地址）
python tests/perf/perf_test.py -q tests/perf/questions.json -k <API_KEY> -b https://kf.dev.youbanban.com

# 自定义 workflow（每个 session 可独立指定 workflow，脚本内全局 -w 为默认值）
python tests/perf/perf_test.py -q tests/perf/questions.json -w auto_film

# 输出详细结果到 JSON 文件
python tests/perf/perf_test.py -q tests/perf/questions.json -o results.json

# 并发模式（多个 session 同时执行，需要 API 端支持）
python tests/perf/perf_test.py -q tests/perf/questions.json -p 4
```

### 参数说明

| 参数 | 简写 | 默认值 | 说明 |
|------|------|--------|------|
| `--questions-file` | `-q` | 必填 | JSON 问题文件路径 |
| `--api-key` | `-k` | 空 | `X-API-Key` 请求头（空则跳过鉴权） |
| `--base-url` | `-b` | `http://localhost:9000` | KF API 地址，也可通过环境变量 `KF_API_URL` 设置 |
| `--workflow` | `-w` | `auto_film` | 默认 workflow 名称（可按 session 覆盖） |
| `--parallel` | `-p` | `1` | 并发 session 数（1 = 串行） |
| `--output` | `-o` | 无 | 结果输出 JSON 文件路径 |

## 输出报告

```
========================================================================
  Results Summary
========================================================================
  Total time     : 45.2s
  Total requests : 200
  Success        : 200
  Failed         : 0
  Avg latency    : 226ms
  Min latency    : 89ms
  Max latency    : 1.2s
  P50            : 210ms
  P90            : 450ms
  P95            : 680ms
  P99            : 980ms
  Finished       : 2026-07-21 23:30:00
========================================================================
```

## 前置条件

1. kf-api 服务已启动（本地默认 `:9000`）
2. kf-embed 服务已启动（`:8100`）
3. Qdrant 已启动（`:6334`）且 `auto_film` collection 已建
4. 如开启鉴权，需提供有效的 `X-API-Key`

本地一键启动：`.\scripts\dev\start-all.ps1`
