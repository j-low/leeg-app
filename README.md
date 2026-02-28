# Leeg

Rec-league hockey team management application. Captains manage rosters, attendance, lineups, messaging, and surveys primarily via SMS, with a React dashboard for complex flows. Players interact via SMS for self-updates (attendance, position preferences).

Built as a learn-and-build project to exercise a **production-grade AI pipeline** end-to-end: input parsing, security guards, hybrid RAG, agentic tool-calling, structured output, PII redaction, observability, and cost-controlled self-hosted inference.

> For full architectural details, entity models, pipeline stages, and technology rationale, see [CLAUDE.PROJECT.MD](CLAUDE.PROJECT.MD).
> For development progress tracking, see [PROJECT_CHECKLIST.md](PROJECT_CHECKLIST.md).

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Backend** | Python 3.12, FastAPI, async/await, Pydantic, Celery |
| **Frontend** | Next.js (React, TypeScript, Tailwind CSS) |
| **LLM** | Ollama + Llama-3.1-8B-Instruct (GGUF Q5, self-hosted) |
| **AI Pipeline** | spaCy (NER), Llama Guard (prompt security), LangGraph (agentic loops), Presidio (PII redaction), LLMLingua (compression), Instructor (structured output) |
| **Vector DB** | Qdrant (hybrid dense+sparse search) |
| **Database** | PostgreSQL (app entities), Redis (caching, Celery broker) |
| **SMS** | Twilio (inbound/outbound + OTP verification) |
| **Observability** | OpenTelemetry, Prometheus, Grafana, Loki, Jaeger |
| **Deployment** | Docker Compose, single-server |

## Architecture

```
SMS (Twilio) ──► FastAPI Webhook ──► Celery Task ──┐
                                                    │
Dashboard (Next.js) ──► FastAPI REST/SSE ──────────┤
                                                    ▼
                                            ┌──────────────┐
                                            │   Pipeline    │
                                            ├──────────────┤
                                            │ 1. Preprocess │ spaCy NER, intent, guards
                                            │ 2. RAG        │ Qdrant hybrid search, rerank, compress
                                            │ 3. Generate   │ Ollama LLM, tool calls, agent loop
                                            │ 4. Postprocess│ PII redact, validate, format
                                            └──────┬───────┘
                                                   │
                                    ┌──────────────┼──────────────┐
                                    ▼              ▼              ▼
                                Postgres        Qdrant         Twilio
                               (entities)     (vectors)     (SMS out)
```

## Local Development

```bash
# Start backing services
docker compose up postgres redis -d

# Activate venv and run API
source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Run Celery worker (separate terminal)
celery -A app.tasks.celery_app worker --loglevel=info

# Seed dev data
python scripts/seed_data.py
```

To test inbound SMS locally, expose port 8000 via ngrok and point your Twilio
webhook to `https://<ngrok-id>.ngrok-free.app/sms/webhook`.  Leave
`TWILIO_ACCOUNT_SID` empty in `.env` to skip signature validation when
developing without a real Twilio account.

## Project Status

See [PROJECT_CHECKLIST.md](PROJECT_CHECKLIST.md) for detailed progress.
