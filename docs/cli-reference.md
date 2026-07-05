# CLI 参考手册

KF 提供 3 个命令行工具：文档入库、知识库管理、工作流校验。

---

## 1. 文档入库 — `python -m src.cli.build`

扫描目录中的文档文件，分块、向量化、写入 Qdrant。

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--dir` | str | `data/documents` | 源文件目录路径 |
| `--collection` | str | `default` | 目标 Qdrant 集合名 |
| `--chunk-size` | int | `800` | 分块字符数（按字符计，中文友好） |
| `--chunk-overlap` | int | `128` | 相邻块重叠字符数 |
| `--qdrant-host` | str | `localhost` | Qdrant 主机地址 |
| `--qdrant-port` | int | `6334` | Qdrant gRPC 端口 |
| `--ollama-url` | str | `http://localhost:11434/v1` | Ollama 地址 |
| `--embed-model` | str | `nomic-embed-text` | 嵌入模型名 |
| `--extensions` | str | (空) | 逗号分隔的扩展名。空 = 自动检测全部支持格式 |

### 支持格式

| 格式 | 扩展名 | 依赖 |
|------|--------|------|
| 纯文本 | `.txt` | 无 |
| Markdown | `.md` | 无 |
| PDF | `.pdf` | `pip install pymupdf` |
| Word | `.docx` | `pip install python-docx` |
| Excel | `.xlsx` | `pip install openpyxl` |
| CSV | `.csv` | 无 |
| HTML | `.html` `.htm` | 无 |

### 使用示例

```bash
# 基础用法：自动检测所有格式，导入到 default 集合
python -m src.cli.build

# 指定目录和集合名
python -m src.cli.build --dir data/faq_docs --collection faq_kb

# 自定义分块大小（小文本推荐）
python -m src.cli.build --dir data/kb --collection kb --chunk-size 400 --chunk-overlap 64

# 自定义分块大小（长文档推荐）
python -m src.cli.build --dir data/manuals --collection manuals --chunk-size 1500 --chunk-overlap 200

# 仅导入 Markdown 和 PDF
python -m src.cli.build --extensions .md,.pdf

# 指定远程 Qdrant 和 Ollama
python -m src.cli.build \
  --qdrant-host 10.0.0.5 --qdrant-port 6334 \
  --ollama-url http://gpu-server:11434/v1 \
  --embed-model nomic-embed-text

# 环境变量
export QDRANT_HOST=10.0.0.5
export OLLAMA_HOST=http://gpu-server:11434/v1
export BUILD_DIR=data/kb
export CHUNK_SIZE=1000
python -m src.cli.build
```

---

## 2. 知识库管理 — `python -m src.cli.manage`

管理 Qdrant 中的集合和文档。全局参数 `--qdrant-host` `--qdrant-port` 在所有子命令中可用。

### 子命令

#### `list` — 列出所有集合

```bash
python -m src.cli.manage list
# 输出:
# kb
# faq_kb
# l2_test
```

#### `info` — 集合详情

```bash
python -m src.cli.manage info kb
# 输出:
# {
#   "name": "kb",
#   "points_count": 342,
#   "vectors_count": 342,
#   "indexed_vectors_count": 0,
#   "segments_count": 8,
#   "config": { ... }
# }
```

#### `count` — 文档总数

```bash
python -m src.cli.manage count kb
# 输出:
# kb: 342 points
```

#### `browse` — 分页浏览内容

```bash
# 查看前 10 条
python -m src.cli.manage browse kb --limit 10

# 从第 20 条开始
python -m src.cli.manage browse kb --limit 10 --offset 20

# 遍历全部
python -m src.cli.manage browse kb --limit 20 --all
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--limit` | int | 20 | 每页条数 |
| `--offset` | int | 0 | 起始偏移 |
| `--all` | flag | false | 遍历全部页面 |

#### `search` — 语义检索

```bash
# 搜索 "退款政策"
python -m src.cli.manage search kb "退款政策"

# 限制返回 3 条
python -m src.cli.manage search kb "产品价格" --limit 3

# 设置分数阈值
python -m src.cli.manage search kb "部署方式" --score-threshold 0.6
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--limit` | int | 5 | 返回条数 |
| `--ollama-url` | str | `http://localhost:11434/v1` | Ollama 地址 |
| `--embed-model` | str | `nomic-embed-text` | 嵌入模型 |
| `--score-threshold` | float | (无) | 最低相似度分数 |

#### `delete` — 删除集合

```bash
# 交互确认
python -m src.cli.manage delete test_kb
# Delete collection 'test_kb'? [y/N]: y
# Deleted: test_kb

# 跳过确认
python -m src.cli.manage delete test_kb --yes
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--yes` / `-y` | flag | false | 跳过确认 |

#### 远程连接

```bash
python -m src.cli.manage list --qdrant-host 10.0.0.5 --qdrant-port 6334
```

---

## 3. 工作流校验 — `python -m src.cli.validate_workflow`

校验工作流定义的正确性。

### 用法

```bash
# 校验单个工作流
python -m src.cli.validate_workflow config/workflows/customer_service/workflow.yaml

# 校验产品目录
python -m src.cli.validate_workflow config/workflows/customer_service

# 显示详细校验过程
python -m src.cli.validate_workflow config/workflows/default --verbose

# 校验所有工作流
for d in config/workflows/*/; do
    python -m src.cli.validate_workflow "$d"
done
```

### 校验项目

| 检查项 | 说明 |
|--------|------|
| 文件存在 | workflow.yaml + nodes/*.yaml 路径有效 |
| 节点名唯一 | 无重名节点 |
| next_type 合法 | 必须为 `one` `if-then` `switch` 之一 |
| 节点引用有效 | next 引用的节点在 nodes 中已定义 |
| 无孤立节点 | 除终止节点外，每个节点都能从起始节点到达 |
| 无死胡同 | 除终止节点外，每个节点都有后继（next 非空） |

### 输出示例

```
PASS: workflow 'customer_service' (5 nodes, 0 errors)
```
或
```
FAIL: workflow 'customer_service' (5 nodes, 2 errors)
  ERROR: node 'missing_handler' referenced but not found in nodes/
  ERROR: node 'orphan_node' is unreachable from start
```

---

## 分块策略指南

| 场景 | chunk_size | chunk_overlap | 说明 |
|------|-----------|---------------|------|
| FAQ 短问答 | 200-400 | 50 | 短文本，小 chunk 精度高 |
| 产品文档 | 800 | 128 | **默认值**，中文通用 |
| 技术手册 | 1000-1500 | 200 | 长段落，保留更多上下文 |
| 法律合同 | 500-800 | 100 | 精确段落级切分 |

### 计数方式

chunk_size 按**字符数**计算（`len(text)`），非单词数。对中英文均友好。

### 分块流程

```
文档 → 按 \n\n+ 分段 → 逐段合并到 chunk_size → 相邻块 overlap 字符重叠 → 输出
```
