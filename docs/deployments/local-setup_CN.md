[English](local-setup_EN.md)

# 本地开发环境

最快 5 分钟跑起来。

## 方式一：Docker Compose（推荐）

```bash
# 1. 配置
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY=sk-...

# 2. 启动
docker compose up -d --build

# 3. 验证
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/workflows
```

## 方式二：手动启动

```bash
# 1. Python 环境
python -m venv venv && source venv/bin/activate   # Linux/Mac
python -m venv venv && venv\Scripts\activate      # Windows
pip install -e ".[dev]"

# 2. Qdrant（Docker）
docker run -d --name qdrant -p 6333:6333 -p 6334:6334 qdrant/qdrant:latest

# 3. kf-embed（Docker，或本地进程）
docker build -t kf-embed -f Dockerfile.embed . && docker run -d --name kf-embed -p 8100:8100 kf-embed

# 4. 配置
cp .env.example .env && vim .env

# 5. 启动 API
uvicorn src.api.main:app --reload --port 9000

# 6. 验证
curl http://localhost:9000/health
```

## 日常开发

| 操作 | 命令 |
|------|------|
| 启动 API | `uvicorn src.api.main:app --reload --port 9000` |
| 启动前端 | `cd src/gui/ui && npm run dev`（代理到 `:9000`，端口 5173） |
| 运行测试 | `pytest tests/unit/ -q && pytest tests/api/ -q` |
| 代码检查 | `ruff check src/` |

## 数据库

默认使用 SQLite（`data/metrics.db`，自动创建）。切换 MySQL/PostgreSQL 见 `../deployments/metrics-db-setup.md`。

## 停止服务

```bash
# Docker Compose
docker compose down

# 手动启动
docker stop qdrant kf-embed
```
