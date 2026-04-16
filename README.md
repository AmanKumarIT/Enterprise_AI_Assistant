# Enterprise Knowledge Assistant

An AI-powered enterprise knowledge assistant that answers questions across multiple data sources using advanced RAG, hybrid retrieval, and multi-agent routing.

## Supported Data Sources

- **PDF / DOCX / TXT** — File uploads
- **GitHub** — Repository code
- **SQL Databases** — Schema + data
- **Slack** — Channel messages
- **Confluence / Notion** — Wiki pages
- **Jira** — Tickets & issues

## Architecture

```
┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│   React UI   │───▶│  FastAPI     │───▶│  PostgreSQL  │
│  (Vite + TS) │    │  Backend     │    │              │
└──────────────┘    │              │    └──────────────┘
                    │  ┌────────┐  │    ┌──────────────┐
                    │  │  RAG   │  │───▶│   Qdrant     │
                    │  │Pipeline│  │    │  (Vectors)   │
                    │  └────────┘  │    └──────────────┘
                    │  ┌────────┐  │    ┌──────────────┐
                    │  │LangGrph│  │───▶│   Redis      │
                    │  │ Agent  │  │    │  (Cache/MQ)  │
                    │  └────────┘  │    └──────────────┘
                    └──────┬───────┘
                           │
                    ┌──────┴───────┐
                    │   Celery     │
                    │  Workers     │
                    └──────────────┘
```

## Quick Start

### Development

```bash
# 1. Start infrastructure
docker-compose up -d postgres redis qdrant

# 2. Backend
cd backend
cp .env.example .env
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

# 3. Frontend
cd frontend
npm install
npm run dev
```

### Full Stack (Docker)

```bash
docker-compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Testing

```bash
cd backend
pip install pytest pytest-asyncio httpx
pytest tests/ -v
```

## Deployment

### Kubernetes

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/config.yaml
kubectl apply -f k8s/infrastructure.yaml
kubectl apply -f k8s/deployments.yaml
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Recharts |
| Backend | FastAPI, SQLAlchemy 2.0, Pydantic v2 |
| RAG | LangGraph, LangChain, Cross-Encoder Reranking |
| Vector DB | Qdrant |
| Database | PostgreSQL 15 |
| Queue | Celery + Redis |
| Embedding | SentenceTransformers / OpenAI |
| LLM | OpenAI GPT-4o-mini (configurable) |
| DevOps | Docker, Kubernetes, GitHub Actions |

## License

MIT
