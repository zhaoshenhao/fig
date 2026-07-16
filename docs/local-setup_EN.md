# Local Development Setup

[中文](local-setup_CN.md)

## 1. Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | >=3.12 | Runtime |
| Node.js | >=20 | Build Vue SPA |
| Docker | latest | Run Qdrant + kf-embed |

## 2. Quick Start (docker-compose)

```bash
docker compose up --build
```

This starts the following services:

| Service | Port | Protocol |
|---------|------|----------|
| Qdrant | 6334 | gRPC |
| kf-embed | 8100 | HTTP |
| kf-api | 8000 | HTTP |

## 3. Manual Setup

### 3.1 Clone & Environment

```bash
git clone <repo-url>
cd kf
cp .env.example .env
# Edit .env: add DEEPSEEK_API_KEY
```

### 3.2 Start Qdrant

```bash
docker run -d --name kf-qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v qdrant_data:/qdrant/storage \
  qdrant/qdrant
```

> Port 6333 = HTTP REST API, 6334 = gRPC (used by the SDK).

### 3.3 Start kf-embed (Embedding Service)

kf-embed is a lightweight embedding microservice built on [FastEmbed](https://github.com/qdrant/fastembed), Qdrant's official ONNX inference library. It runs on CPU via ONNX Runtime and provides an OpenAI-compatible `/v1/embeddings` API.

**Docker (recommended — model baked into image, zero download):**

```bash
docker build -t kf-embed -f Dockerfile.embed .
docker run -d --name kf-embed -p 8100:8100 kf-embed
```

**Or run as a local process:**

```bash
pip install -e .[embed]
uvicorn src.embed_service.app:app --port 8100
```

> The model `nomic-ai/nomic-embed-text-v1.5` (768d, 137M params) is pre-downloaded during the Docker build stage into `/opt/fastembed_cache`. `GET /ready` returns 200 once the model is loaded into memory.

### 3.4 Python Environment

```bash
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -e .[dev]
```

### 3.5 Configure Environment Variables (.env)

```
DEEPSEEK_API_KEY=sk-xxx
EMBED_BASE_URL=http://localhost:8100/v1
EMBED_MODEL=nomic-embed-text
QDRANT_HOST=localhost
QDRANT_PORT=6334
```

### 3.6 Build Vue SPA

```bash
cd src/gui/ui
npm install
npm run build
```

### 3.7 Start API

```bash
uvicorn src.api.main:app --reload --port 9000
```

The API serves both REST endpoints (`/api/v1/*`) and the Vue SPA static files (`/`).

## 4. Architecture (local)

```
localhost:8100          ← kf-embed (Docker, FastEmbed ONNX inference)
localhost:6334 (gRPC)   ← Qdrant (Docker)
localhost:6333 (HTTP)   ← Qdrant (REST API)
localhost:9000          ← FastAPI (REST API + Vue SPA static files)
External                ← DeepSeek API (LLM)
```

## 5. Development Workflow

**Hot-reload API:** `uvicorn --reload` auto-restarts on code changes.

**Frontend dev with hot-reload:**

```bash
cd src/gui/ui && npm run dev
# Vite dev server proxies /api/v1 → localhost:9000
```

**Run tests:**

```bash
pytest
pytest -k "dag" -v
```

**Lint:**

```bash
ruff check .
```

**Build docs (ingestion):**

```bash
python -m src.cli.build --dir data/documents --collection default
```

**Validate workflows:**

```bash
python -m src.cli.validate_workflow config/workflows/auto_film/
```

## 6. kf-embed Service Details

### 6.1 Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `EMBED_MODEL` | No | `nomic-ai/nomic-embed-text-v1.5` | FastEmbed model name |
| `EMBED_WARMUP` | No | `1` | Preload model at startup (`0` = lazy) |
| `EMBED_API_KEY` | No | (empty = no auth) | Internal auth key |
| `FASTEMBED_CACHE_PATH` | No | System temp | Model cache path |

### 6.2 API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | Skip | Liveness probe |
| `GET` | `/ready` | Skip | Readiness probe (returns 200 when model loaded) |
| `POST` | `/v1/embeddings` | Key optional | OpenAI-compatible embeddings |

**Auth logic:**

- `EMBED_API_KEY` not set → all requests allowed (dev mode)
- `EMBED_API_KEY` set → `/health` and `/ready` skip auth; `/v1/embeddings` requires `X-API-Key: <key>` or `Authorization: Bearer <key>`

### 6.3 Embedding Request/Response

**Request:**

```json
{"model": "nomic-embed-text", "input": "text to embed"}
```

> Model alias: `nomic-embed-text` → `nomic-ai/nomic-embed-text-v1.5`.<br>
> `input` accepts a single string or an array of strings.

**Response:**

```json
{
  "object": "list",
  "data": [{"object": "embedding", "index": 0, "embedding": [0.01, -0.02, ...]}],
  "model": "nomic-embed-text",
  "usage": {"prompt_tokens": 2, "total_tokens": 2}
}
```

### 6.4 Startup Times

| Environment | Time to Ready |
|-------------|---------------|
| Local process (cached model) | ~1.3s |
| Docker (baked model) | ~1.5s |
| Cold start (download required) | ~60s (not recommended—bake into image) |

### 6.5 Troubleshooting

| Symptom | Cause | Solution |
|---------|-------|----------|
| `/ready` returns 503 | Model not loaded | Check `EMBED_WARMUP=1` and startup logs |
| Empty vectors returned | Empty input | Check request `input` field |
| 401 Unauthorized | Key mismatch or missing | Check `EMBED_API_KEY` env var |
| Slow startup | First-time model download | Ensure model is baked into image or cached locally |

## 7. Stopping

```bash
docker stop kf-embed kf-qdrant && docker rm kf-embed kf-qdrant
# Or: docker compose down
# Ctrl+C to stop uvicorn
```

## 8. Optional: Vue SPA Development

The Vue 3 + Vite SPA lives in `src/gui/ui/`. For frontend-only development:

```bash
cd src/gui/ui
npm run dev      # Dev server with HMR, proxies API calls to localhost:9000
npm run build    # Production build → dist/
```
