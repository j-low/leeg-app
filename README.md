# Leeg

Rec-league hockey team management application. Captains manage rosters, attendance, lineups, messaging, and surveys — primarily via SMS, with a React dashboard for complex flows. Players interact entirely over SMS for self-service updates (attendance, position preferences, sub requests).

All natural-language input — from SMS or the dashboard — is processed by a multi-stage AI pipeline: NLP preprocessing and security screening, hybrid vector retrieval, an agentic LLM reasoning loop with database tool use, and a post-processing stage that enforces PII redaction and channel-specific formatting before any response is delivered.

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Backend** | Python 3.12, FastAPI, async/await, Pydantic v2, SQLAlchemy async, Alembic, Celery |
| **Frontend** | Next.js 15, React 19, TypeScript, Tailwind CSS 4, Server-Sent Events |
| **LLM** | Claude Haiku (Anthropic API) — generation and tool calling |
| **Security guard** | Llama Guard 3 8B via Ollama (self-hosted) — content safety screening |
| **AI pipeline** | spaCy (NER + custom entity rules), LangGraph (ReAct agent loop), Instructor (structured output), LLMLingua (prompt compression), Presidio (PII detection + redaction) |
| **Vector DB** | Qdrant — hybrid dense + sparse (BM42) search with cross-encoder reranking |
| **Embeddings** | `nomic-embed-text-v1.5` via sentence-transformers |
| **Database** | PostgreSQL 16 (application entities), Redis 7 (embedding cache, Celery broker, pipeline result cache) |
| **SMS** | Twilio (inbound webhook with signature validation, outbound send) |
| **Observability** | OpenTelemetry (tracing), Prometheus + Grafana (metrics dashboards), Loki + Promtail (log aggregation), Jaeger (distributed trace UI) |
| **Deployment** | Docker Compose, multi-stage Dockerfiles, non-root containers |

## Architecture

```
SMS (Twilio) ──► FastAPI /sms/webhook ──► Celery task ──┐
                                                         │
Dashboard (Next.js) ──► FastAPI REST/SSE ───────────────┤
                                                         ▼
                                               ┌──────────────────┐
                                               │    AI Pipeline    │
                                               ├──────────────────┤
                                               │ 1. Preprocess     │
                                               │ 2. RAG            │
                                               │ 3. Generate       │
                                               │ 4. Postprocess    │
                                               └────────┬─────────┘
                                                        │
                                       ┌────────────────┼────────────────┐
                                       ▼                ▼                ▼
                                   Postgres           Qdrant           Twilio
                                  (entities)         (vectors)       (SMS out)
```

## AI Pipeline

Every inbound message — SMS or dashboard — passes through four sequential stages before a response is delivered. The pipeline is fully async; the dashboard channel additionally streams tokens to the browser over SSE as they are generated.

### Stage 1 — Preprocessing & Security Guards (`app/stages/preprocess/`)

Raw text is transformed into a typed `StructuredInput` before any LLM is consulted.

**NER & entity extraction** (`preprocess.py`): spaCy `en_core_web_sm` extracts standard entities (persons, dates, times, locations). A custom `EntityRuler` layer — inserted before the standard NER component — adds hockey-domain labels: `HOCKEY_POSITION` (center, wing, defense, goalie), `ATTENDANCE_YES`, and `ATTENDANCE_NO`. The extracted `EntityMap` feeds directly into intent classification.

**Intent classification** (`preprocess.py`): A keyword + entity heuristic (no LLM required) maps the message to one of seven intents: `attendance_update`, `lineup_request`, `preference_update`, `sub_request`, `schedule_query`, `survey_response`, or `query`. Each intent carries a confidence score; the classification is O(n) over token count.

**Security guards** (`guards.py`): Two-layer defense-in-depth.
- *Layer 1 — Regex fast-path*: Nine compiled patterns catch well-known prompt injection strings in under 1ms (instruction override, role-play jailbreaks, delimiter injection, system prompt probing).
- *Layer 2 — Llama Guard 3*: For messages passing the regex check, Llama Guard 3 8B (running locally via Ollama) performs LLM-based content safety classification. Degrades gracefully to fail-open if Ollama is unreachable; the regex layer is the primary guard.

A `SecurityError` raised here short-circuits the entire pipeline — the LLM is never invoked on rejected inputs.

---

### Stage 2 — Hybrid RAG (`app/stages/retrieval/`)

Grounds LLM responses in factual, team-specific data. Skipped entirely for intents that do not require document context (e.g. `attendance_update`).

**Embedding & ingestion** (`app/rag/embeddings.py`, `app/rag/ingestion.py`): Team entities from Postgres (roster details, player preferences, game history, past lineups, survey responses) are chunked with `RecursiveCharacterTextSplitter` (chunk_size=512, overlap=50) and embedded with `nomic-embed-text-v1.5`. Embeddings are upserted to a Qdrant collection with metadata filters (`team_id`, `doc_type`, `last_updated`). A Redis cache layer avoids re-embedding unchanged documents. A Celery task triggers incremental re-ingestion on DB writes.

**Hybrid retrieval** (`app/rag/retriever.py`): Qdrant hybrid search fuses dense vector similarity with sparse BM42 keyword matching. Queries are filtered by `team_id` and `season_id` from the pipeline context, so each captain's responses are grounded in their own team's data only. Results are cached in Redis (keyed by query hash) with a configurable TTL to avoid redundant network round-trips.

**Cross-encoder reranking** (`app/rag/reranker.py`): The top-10 retrieved candidates are re-scored by a cross-encoder (`BAAI/bge-reranker-v2-m3`) and trimmed to the top 5. Cross-encoders attend to query–document interaction jointly, substantially improving precision over the bi-encoder retrieval score alone.

**Prompt compression** (`app/stages/retrieval/rag.py`): The reranked chunks are passed through LLMLingua (`PromptCompressor`) at a 0.5 compression ratio, halving the token count of the context block while preserving key facts. This directly controls LLM input token cost and reduces the risk of attention dilution over long contexts.

---

### Stage 3 — Generation & Agentic Tool Calling (`app/stages/generation/`)

A LangGraph ReAct agent loop drives multi-step reasoning. Claude Haiku is the LLM; it reasons over the compressed context, emits tool calls as needed, receives results, and iterates until it produces a final answer.

**Prompt assembly** (`prompts.py`): Jinja2 templates render the system prompt (role, constraints, output format) and user turn (structured input, compressed RAG context, conversation channel). The system prompt is constant across agent turns; the user turn is constructed once before the loop begins.

**LangGraph state machine** (`agent.py`): A `StateGraph` with two nodes — `call_llm` and `execute_tools` — implements the ReAct cycle. The routing function inspects Claude's `stop_reason`: `tool_use` routes to tool execution; `end_turn` or `max_tokens` terminates the graph. Safety bounds: max 5 iterations, 30s per step, 120s total.

**Tool calling** (`tools.py`): Eight tools are registered and passed to the Anthropic API as typed schemas. Claude reasons about which to call and with what arguments; the agent executes them against the live database and feeds results back as `tool_result` blocks in the next turn.

| Tool | Effect |
|------|--------|
| `get_roster` | Read current player list for a team |
| `get_attendance` | Read all attendance records for a game |
| `update_attendance` | Upsert a player's attendance status (yes/no/maybe) |
| `get_player_prefs` | Read a player's position preferences and constraints |
| `update_player_prefs` | Update a player's position preferences |
| `search_schedule` | Query upcoming games for a team |
| `send_sms` | Send an SMS to a single player via Twilio |
| `send_group_sms` | Broadcast an SMS to a list of players via Twilio |

All write tools use upsert semantics, making them safe to retry across agent loop iterations.

**Streaming** (`agent.py → stream_agent()`): For the dashboard channel, `stream_agent()` uses the Anthropic streaming API. Text tokens are yielded as SSE `answer_token` events as they arrive; `tool_start` and `tool_result` events are emitted around each tool execution. The browser renders tokens incrementally and shows live tool-call badges.

---

### Stage 4 — Post-processing (`app/stages/postprocess/`)

The raw agent output is transformed into a delivery-ready response. This stage never raises — any unhandled error returns a safe fallback message.

**Validation** (`postprocess.py`): The answer string is extracted and checked for emptiness. Missing or blank answers produce a fallback message and a `fallback:empty_answer` mutation tag in the audit log.

**PII redaction** (`pii.py`): Presidio `AnalyzerEngine` scans the answer for personally identifiable information (phone numbers, email addresses, names, locations). Detected entities are replaced with typed placeholders (e.g. `<PHONE_NUMBER>`). A roster-aware name suppressor additionally redacts known player names injected by the pipeline orchestrator, preventing the model from leaking roster data to the wrong recipients. Redaction events are recorded as `pii_redacted` mutation tags.

**Channel formatting** (`formatter.py`):
- *SMS*: Enforces a 1,600-character length limit (Twilio's concatenated SMS ceiling); truncates with a continuation notice if exceeded. Strips markdown and ensures GSM-7 encoding compatibility.
- *Dashboard*: Wraps the response in a structured JSON payload with tool call metadata for the frontend to render.

**Audit logging**: A structlog entry records channel, intent, team ID, PII detection flag, truncation flag, full mutation list, output length, tool call count, iteration count, and stop reason — without logging the response text itself.

---

## Services

| Service | Port | Purpose |
|---------|------|---------|
| FastAPI (`api`) | 8000 | REST API + SSE chat endpoint |
| Next.js (`frontend`) | 3000 | Dashboard |
| PostgreSQL | 5432 | Application data |
| Redis | 6379 | Cache + Celery broker |
| Qdrant | 6333 | Vector store |
| Ollama | 11434 | Llama Guard 3 inference |
| Celery worker | — | Async SMS processing tasks |
| Prometheus | 9090 | Metrics scraping |
| Grafana | 3001 | Metrics + log dashboards |
| Loki | 3100 | Log aggregation |
| Jaeger | 16686 | Distributed trace UI |
| OTel Collector | 4317/4318 | Trace + metric export |

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) — runs all services
- Python 3.12 + pip — for running tests locally without Docker
- Node.js 20 + npm — for frontend development without Docker

## Quick Start

```bash
# 1. Clone and configure
git clone <repo-url> leeg-app && cd leeg-app
cp .env.production.example .env   # fill in real values

# 2. Start everything
make dev
# or: docker compose up --build

# 3. Open the app
open http://localhost:3000         # Next.js dashboard
open http://localhost:8000/docs    # FastAPI Swagger UI
open http://localhost:3001         # Grafana (admin / admin)
open http://localhost:16686        # Jaeger trace UI
```

## Development

```bash
make test          # Run all tests with coverage
make test-unit     # Unit tests only (fast, no DB)
make lint          # ruff + eslint
make typecheck     # mypy + tsc

make migrate       # Apply Alembic migrations
make seed          # Seed sample data
make ingest        # Ingest docs into Qdrant

make load-test     # Locust load test (requires running backend on :8000)
```

### Running the backend without Docker

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
docker compose up postgres redis qdrant -d  # backing services only
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Celery worker (separate terminal)
celery -A app.tasks.celery_app worker --loglevel=info
```

### Testing inbound SMS locally

Expose port 8000 via ngrok and point your Twilio webhook to
`https://<ngrok-id>.ngrok-free.app/sms/webhook`. Leave `TWILIO_ACCOUNT_SID`
empty in `.env` to skip signature validation in dev.

## Environment Variables

See [.env.production.example](.env.production.example) for a full list of required variables with descriptions.

## CI

GitHub Actions runs on every push to `main` and every pull request:

| Job | Steps |
|-----|-------|
| **backend** | `ruff` lint → `mypy` typecheck → `pytest` (unit + integration + e2e) with coverage upload |
| **frontend** | `tsc` typecheck → `eslint` lint → `next build` |
| **docker** | `docker build` for both images (runs after backend + frontend pass) |
