[中文](local-setup_CN.md)

# Local Development

Get running in under 5 minutes.

## Option 1: Docker Compose (Recommended)

```bash
# 1. Configure
cp .env.example .env
# Edit .env: set DEEPSEEK_API_KEY=sk-...

# 2. Start
docker compose up -d --build

# 3. Verify
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/workflows
```

## Option 2: Manual Setup

```bash
# 1. Python environment
python -m venv venv && source venv/bin/activate   # Linux/Mac
python -m venv venv && venv\Scripts\activate      # Windows
pip install -e ".[dev]"

# 2. Qdrant (Docker)
docker run -d --name qdrant -p 6333:6333 -p 6334:6334 qdrant/qdrant:latest

# 3. kf-embed (Docker or local process)
docker build -t kf-embed -f Dockerfile.embed . && docker run -d --name kf-embed -p 8100:8100 kf-embed

# 4. Configure
cp .env.example .env && vim .env

# 5. Start API
uvicorn src.api.main:app --reload --port 9000

# 6. Verify
curl http://localhost:9000/health
```

## Daily Workflow

| Task | Command |
|------|---------|
| Start API | `uvicorn src.api.main:app --reload --port 9000` |
| Start frontend | `cd src/gui/ui && npm run dev` (proxies to `:9000`, port 5173) |
| Run tests | `pytest tests/unit/ -q && pytest tests/api/ -q` |
| Lint | `ruff check src/` |

## Database

Default is SQLite (`data/metrics.db`, auto-created). To switch to MySQL/PostgreSQL see `../deployments/metrics-db-setup_EN.md`.

## Stopping Services

```bash
# Docker Compose
docker compose down

# Manual
docker stop qdrant kf-embed
```
