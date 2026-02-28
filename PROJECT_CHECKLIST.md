# Leeg - Project Development Checklist

> **Reference Document:** All architectural decisions, technology choices, entity models, pipeline stages, and non-functional requirements are defined in [CLAUDE.PROJECT.MD](CLAUDE.PROJECT.MD). This checklist is a derivative of that document and should always be read in conjunction with it.

> **Agent Instructions:**
> 1. **Before starting any step**, explain to the user what the step accomplishes, how it fits into the overall project architecture, and which concerns of a modern AI pipeline it addresses (e.g., security, observability, cost control, structured output, agentic reasoning, etc.).
> 2. **After completing a step**, ask the user: *"Are you satisfied with the work for this step?"* Only check the corresponding box after receiving explicit confirmation.
> 3. **When resuming work in a new thread**, read this checklist first to determine the current state of progress, then read [CLAUDE.PROJECT.MD](CLAUDE.PROJECT.MD) for full architectural context before proceeding.
> 4. **Update this file** by replacing `[ ]` with `[x]` for the confirmed step.

---

## Phase 1 - Project Initialization & Skeleton

**Pipeline concern:** Foundation & infrastructure -- establishing the monorepo structure, dependency management, containerized services, and development workflow that all subsequent pipeline stages depend on.

- [x] **1.1** Initialize Git repository with `.gitignore` (Python venv, `__pycache__`, `.env`, node_modules, Docker volumes, IDE files)
- [x] **1.2** Create `README.md` with project overview (name, objective, tech stack summary referencing CLAUDE.PROJECT.MD)
- [x] **1.3** Set up Python 3.12 virtual environment; create `requirements.txt` with core dependencies: `fastapi`, `uvicorn[standard]`, `pydantic`, `sqlalchemy`, `psycopg2-binary`, `alembic`, `structlog`, `python-dotenv`
- [x] **1.4** Create backend project structure:
  ```
  app/
    __init__.py
    main.py          # FastAPI app factory, /health endpoint
    config.py        # Pydantic Settings for env vars
    db.py            # SQLAlchemy engine, session factory
    models/          # SQLAlchemy ORM models (one file per entity)
      __init__.py
    schemas/         # Pydantic request/response schemas
      __init__.py
    routes/          # API route modules
      __init__.py
    stages/          # AI pipeline stage modules
      __init__.py
    services/        # Business logic layer
      __init__.py
    pipeline.py      # Orchestrator (stub)
  ```
- [x] **1.5** Create `app/main.py` with FastAPI app, `/health` endpoint returning `{"status": "ok"}`, basic CORS middleware
- [x] **1.6** Create `app/config.py` using Pydantic `BaseSettings` for environment variables (`DATABASE_URL`, `REDIS_URL`, `TWILIO_*`, `OLLAMA_HOST`, `QDRANT_HOST`, `SECRET_KEY`, `DEBUG`)
- [x] **1.7** Create `.env.example` with all expected environment variables documented
- [x] **1.8** Create `docker-compose.yml` with initial services: `app` (FastAPI), `postgres` (with volume + healthcheck), `redis` (with healthcheck). Bind appropriate ports; use `.env` for config
- [x] **1.9** Verify stack: `docker compose up`, confirm `/health` returns 200, confirm Postgres and Redis are reachable from the app container
- [x] **1.10** Initialize Next.js frontend in `frontend/` directory with TypeScript (`npx create-next-app@latest frontend --typescript --tailwind --app --src-dir`); verify `npm run dev` works

---

## Phase 2 - Data Models & Database

**Pipeline concern:** Structured data layer -- the entities that the AI pipeline will query, mutate via tool calls, and embed into the vector store for RAG grounding. Proper schema design ensures tool-calling reliability and structured output validation.

- [ ] **2.1** Create SQLAlchemy ORM models in `app/models/`:
  - `team.py`: `Team` table (id, name, captain_id FK, created_at, updated_at)
  - `player.py`: `Player` table (id, name, phone unique, team_id FK, position_prefs JSON array, skill_notes text, sub_flag bool, captain_notes text)
  - `season.py`: `Season` table (id, name, start_date, end_date, status enum[open/closed], created_at)
  - `team_season.py`: `TeamSeason` association table (team_id FK, season_id FK)
  - `game.py`: `Game` table (id, date, time, location, season_id FK nullable, standalone bool, notes text)
  - `attendance.py`: `Attendance` table (id, game_id FK, player_id FK, status enum[yes/no/maybe], updated_at)
  - `lineup.py`: `Lineup` table (id, game_id FK, proposed_lines JSON, criteria text, explanation text, created_at)
  - `player_preference.py`: `PlayerPreference` table (id, player_id FK, position_prefs JSON, ice_time_constraints text, style_notes text, updated_at)
  - `survey.py`: `SurveyResponse` table (id, survey_id, player_id FK, question text, answer text, scope enum[team/season/captain], created_at)
  - `message_log.py`: `MessageLog` table (id, from_phone, to_phones JSON, content text, msg_type enum[reminder/sub_request/survey/blast/system], created_at)
- [ ] **2.2** Create `app/models/__init__.py` exporting `Base` and all models
- [ ] **2.3** Create `app/db.py` with async SQLAlchemy engine, `AsyncSession` factory, `get_db` dependency
- [ ] **2.4** Initialize Alembic: `alembic init migrations`; configure `alembic.ini` and `migrations/env.py` to use `app.config` and `app.models.Base.metadata`
- [ ] **2.5** Generate and apply initial migration: `alembic revision --autogenerate -m "initial_tables"` && `alembic upgrade head`
- [ ] **2.6** Create corresponding Pydantic schemas in `app/schemas/` for each entity (Create, Update, Read variants) with validation rules
- [ ] **2.7** Write a seed script `scripts/seed_data.py` that inserts sample team, players, season, and game data for development
- [ ] **2.8** Verify: run migration, execute seed script, query tables to confirm data integrity and relationships

---

## Phase 3 - Authentication & API Skeleton

**Pipeline concern:** Security boundary -- JWT auth protects dashboard/API routes, phone-based gating secures SMS endpoints. This is the first layer of defense-in-depth, ensuring only authorized users can trigger pipeline flows and access data.

- [ ] **3.1** Add auth dependencies to `requirements.txt`: `python-jose[cryptography]`, `passlib[bcrypt]`, `python-multipart`
- [ ] **3.2** Create `app/auth.py`: JWT token creation/validation utilities, password hashing, `get_current_user` dependency
- [ ] **3.3** Create `app/models/user.py`: `User` table (id, email unique, hashed_password, phone, is_captain bool, is_active bool, created_at)
- [ ] **3.4** Create `app/routes/auth.py`: endpoints for `POST /api/auth/register` (captain registration), `POST /api/auth/login` (returns JWT), `GET /api/auth/me` (current user info)
- [ ] **3.5** Add Alembic migration for the User table
- [ ] **3.6** Create CRUD API route stubs (protected by JWT) in `app/routes/`:
  - `teams.py`: CRUD for teams + roster management
  - `seasons.py`: CRUD for seasons, link/unlink teams
  - `games.py`: CRUD for games, attendance views
  - `lineups.py`: GET lineup history, POST request AI lineup suggestion
- [ ] **3.7** Add rate limiting middleware using `slowapi` on all routes (stricter limits on auth endpoints)
- [ ] **3.8** Add request validation and XSS protection middleware (sanitize inputs)
- [ ] **3.9** Register all routers in `app/main.py` with appropriate prefixes and tags
- [ ] **3.10** Test: register a captain, login, obtain JWT, access protected route, verify 401 on unauthenticated access

---

## Phase 4 - SMS Integration & Inbound Webhook

**Pipeline concern:** External interface -- Twilio provides the SMS channel that is the primary interaction mode. Webhook signature validation is a security concern; Celery async processing ensures the pipeline doesn't block on slow LLM inference, addressing latency and reliability.

- [ ] **4.1** Add SMS dependencies to `requirements.txt`: `twilio`, `celery[redis]`
- [ ] **4.2** Create `app/sms.py`: Twilio client wrapper (send_sms, send_group_sms), inbound signature validation utility
- [ ] **4.3** Create `app/routes/sms.py`: `POST /sms/webhook` endpoint -- validate Twilio signature, extract `from_phone` and `body`, dispatch to Celery task, return TwiML acknowledgment
- [ ] **4.4** Create `app/tasks.py`: Celery app configuration; `process_inbound_sms` task that calls `run_pipeline()` and sends response via Twilio
- [ ] **4.5** Add `celery-worker` service to `docker-compose.yml` (uses Redis as broker)
- [ ] **4.6** Create `app/routes/messaging.py`: captain-initiated endpoints for `POST /api/messages/send` (individual), `POST /api/messages/broadcast` (group), `POST /api/messages/survey` (survey blast)
- [ ] **4.7** Add Twilio webhook URL configuration notes to `.env.example` and `README.md` (ngrok for local dev)
- [ ] **4.8** Test: simulate inbound SMS via curl to webhook endpoint, verify Celery task queued and response sent (mock Twilio in tests)

---

## Phase 5 - Stage 1: Preprocessing & Security Guards

**Pipeline concern:** Input sanitization, entity extraction, intent classification, and prompt injection defense. This is the first AI pipeline stage -- it transforms raw natural language into structured data while enforcing security. Defense-in-depth: regex guards + Llama Guard + rate limiting form multiple security layers.

- [ ] **5.1** Add NLP/security dependencies to `requirements.txt`: `spacy`, `transformers`, `torch` (or `llama-guard` client via Ollama)
- [ ] **5.2** Download spaCy model: `python -m spacy download en_core_web_sm`
- [ ] **5.3** Create `app/schemas/pipeline.py`: `StructuredInput` Pydantic model (raw_text, channel, from_phone, entities dict, intent str, is_safe bool, confidence float, metadata dict)
- [ ] **5.4** Create `app/stages/preprocess.py` with `async def preprocess_input(raw_text: str, context: dict) -> StructuredInput`:
  - spaCy NER pipeline for PERSON, DATE, TIME, LOCATION extraction
  - Custom entity rules for hockey terms (positions: center/wing/defense/goalie, actions: attendance/lineup/preference/query/survey)
  - Intent classification heuristic (keyword + NER-based: attendance_update, lineup_request, preference_update, query, survey_response, sub_request, schedule_query)
  - Return `StructuredInput` with extracted data
- [ ] **5.5** Create `app/stages/guards.py`:
  - Regex-based prompt injection detection (common injection patterns)
  - Llama Guard integration via Ollama for content safety classification
  - Combined `async def check_safety(text: str) -> tuple[bool, str]` returning (is_safe, reason)
- [ ] **5.6** Integrate guards into `preprocess_input` -- reject with `SecurityError` if unsafe; log all rejections with structlog
- [ ] **5.7** Write unit tests in `tests/test_preprocess.py`:
  - Test entity extraction on sample SMS messages ("Bob can't make it Tuesday", "I want to play wing")
  - Test intent classification accuracy
  - Test guard rejection of injection attempts ("ignore all instructions and...")
  - Test safe messages pass through

---

## Phase 6 - Stage 2: Hybrid RAG (Retrieval-Augmented Generation)

**Pipeline concern:** Grounding LLM responses in factual, team-specific data. Hybrid search (dense + sparse vectors) ensures recall; re-ranking improves precision; compression reduces token cost; Redis caching avoids redundant embedding/retrieval calls. This addresses hallucination prevention, cost control, and response quality.

- [ ] **6.1** Add RAG dependencies to `requirements.txt`: `qdrant-client`, `sentence-transformers`, `langchain-text-splitters`, `llmlingua` (or `pyllmlingua`)
- [ ] **6.2** Add `qdrant` service to `docker-compose.yml` (port 6333, with volume)
- [ ] **6.3** Create `app/rag/embeddings.py`: embedding utility using `sentence-transformers` with `nomic-embed-text-v1.5` (or `all-MiniLM-L6-v2` as fallback). Batch embed function with Redis caching of embeddings
- [ ] **6.4** Create `app/rag/ingestion.py`:
  - Chunk entities from Postgres into text documents (roster details, game history, player preferences, past lineups, survey responses)
  - Use `RecursiveCharacterTextSplitter` (chunk_size=512, overlap=50)
  - Embed and upsert to Qdrant collection `leeg_docs` with metadata filters (team_id, season_id, doc_type, last_updated)
  - Incremental upsert: track `last_updated` to avoid re-embedding unchanged data
- [ ] **6.5** Create `app/rag/retriever.py`:
  - `async def retrieve(query: str, context: dict, top_k: int = 10) -> list[dict]`
  - Qdrant hybrid search (dense + sparse vectors with fusion)
  - Metadata filtering by team_id, season_id from context
  - Redis cache layer: cache query hash -> results with TTL
- [ ] **6.6** Create `app/rag/reranker.py`: re-rank retrieved chunks using cross-encoder (`BAAI/bge-reranker-v2-m3` or lighter model); return top-k after re-ranking
- [ ] **6.7** Create `app/stages/rag.py`:
  - `async def retrieve_context(structured_input: StructuredInput, context: dict) -> list[dict]`
  - Calls retriever, re-ranker, then applies LLMLingua compression to reduce token count
  - Returns compressed, relevant context chunks
- [ ] **6.8** Write a one-time ingestion script `scripts/ingest_to_qdrant.py` that reads from Postgres and populates Qdrant
- [ ] **6.9** Create Celery task for incremental re-ingestion triggered on DB writes (roster changes, new games, etc.)
- [ ] **6.10** Write tests in `tests/test_rag.py`:
  - Test embedding generation and caching
  - Test ingestion pipeline (mock Qdrant)
  - Test retrieval with metadata filters
  - Test compression reduces token count

---

## Phase 7 - Stage 3: Generation, Tool Calling & Agentic Loops

**Pipeline concern:** Core LLM reasoning -- prompt engineering with structured output enforcement, tool-calling for real-world side effects (DB writes, SMS sends), and agentic ReAct loops for multi-step reasoning. Uses self-hosted quantized LLM (Llama-3.1-8B Q5) for cost control and privacy. This is the heart of the AI pipeline.

- [ ] **7.1** Add generation dependencies to `requirements.txt`: `ollama`, `langgraph`, `instructor`
- [ ] **7.2** Add `ollama` service to `docker-compose.yml` (GPU passthrough if available, volume for models); pull `llama3.1:8b-instruct-q5_0` model
- [ ] **7.3** Create `app/stages/prompts.py`: Jinja2 prompt templates for each intent type:
  - `attendance_update.j2`: system prompt + context + entities + instructions for attendance tool call
  - `lineup_suggestion.j2`: system prompt + context + roster + preferences + criteria + structured output format
  - `general_query.j2`: system prompt + context + question + answer format
  - `survey_collection.j2`: system prompt + survey context + response parsing
  - Base system prompt establishing the assistant's role, constraints, and output format
- [ ] **7.4** Create `app/stages/tools.py`: tool function definitions (callable by the agent):
  - `update_attendance(game_id, player_id, status)` -> DB write
  - `get_attendance(game_id)` -> DB read
  - `send_sms(to_phone, message)` -> Twilio send
  - `send_group_sms(to_phones, message)` -> Twilio broadcast
  - `suggest_lineup(game_id, criteria)` -> generate lineup from roster/prefs
  - `get_roster(team_id)` -> DB read
  - `get_player_prefs(player_id)` -> DB read
  - `update_player_prefs(player_id, prefs)` -> DB write
  - `search_schedule(query)` -> DB read
  - Each tool has a JSON schema for the LLM and a Python implementation
- [ ] **7.5** Create `app/stages/generate.py`:
  - `async def generate_response(structured_input: StructuredInput, rag_context: list[dict], context: dict) -> dict`
  - Assemble prompt: system template + compressed RAG context + extracted entities + conversation history
  - Call Ollama async API with structured output enforcement (via `instructor` or manual JSON mode)
  - Parse LLM response for tool calls or final answer
- [ ] **7.6** Create `app/stages/agent.py`: LangGraph ReAct agent loop:
  - State graph: `input -> reason -> tool_call -> observe -> reason -> ... -> final_answer`
  - Maximum 5 iterations to prevent runaway loops
  - Tool dispatch: match tool name from LLM output to registered tool functions
  - Feed tool results back into next LLM call
  - Timeout per iteration (30s) and total (120s)
  - Return final structured response
- [ ] **7.7** Write tests in `tests/test_generate.py`:
  - Test prompt assembly produces valid prompts
  - Test tool dispatch routes correctly
  - Test agent loop terminates within max iterations
  - Test structured output parsing (mock LLM responses)

---

## Phase 8 - Stage 4: Post-Processing

**Pipeline concern:** Output validation, PII redaction, and response formatting. Ensures LLM outputs conform to expected schemas (structured output enforcement), removes any PII that leaked through (defense-in-depth for privacy), and formats responses appropriately for SMS vs. dashboard channels.

- [ ] **8.1** Add post-processing dependencies to `requirements.txt`: `presidio-analyzer`, `presidio-anonymizer`
- [ ] **8.2** Create `app/stages/postprocess.py`:
  - `async def postprocess(raw_output: dict, context: dict) -> dict`
  - Pydantic validation of LLM output against expected response schemas
  - Fallback formatting if validation fails (graceful degradation)
- [ ] **8.3** Create `app/stages/pii.py`:
  - Initialize Presidio analyzer with relevant entity recognizers (PHONE_NUMBER, PERSON, EMAIL, etc.)
  - `async def redact_pii(text: str) -> str` -- detect and mask PII in outbound text
  - Custom recognizer for hockey-context names (captain notes should not leak player names to other players)
- [ ] **8.4** Integrate PII redaction into postprocess pipeline (redact before sending to any external channel)
- [ ] **8.5** Add response formatter:
  - SMS channel: truncate to 1600 chars (Twilio limit), plain text, actionable language
  - Dashboard channel: structured JSON with explanation fields, supports rich formatting
- [ ] **8.6** Add audit logging: log every pipeline output (redacted version) with structlog for compliance trail
- [ ] **8.7** Write tests in `tests/test_postprocess.py`:
  - Test PII detection and redaction on sample outputs
  - Test schema validation catches malformed LLM output
  - Test SMS formatting respects character limits
  - Test audit log entries are created

---

## Phase 9 - Pipeline Orchestration & Observability

**Pipeline concern:** End-to-end pipeline wiring, async flow control, caching strategy, and full observability stack (traces, metrics, logs). This is where individual stages become a production system -- with timeouts, retries, circuit breakers, and the ability to diagnose issues via distributed tracing and dashboards.

- [ ] **9.1** Add observability dependencies to `requirements.txt`: `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, `opentelemetry-instrumentation-fastapi`, `prometheus-client`, `python-json-logger`
- [ ] **9.2** Add observability services to `docker-compose.yml`:
  - `prometheus` (port 9090, with config to scrape FastAPI metrics)
  - `grafana` (port 3000, with provisioned datasources for Prometheus + Loki + Jaeger)
  - `loki` (port 3100, log aggregation)
  - `jaeger` (port 16686, distributed tracing UI)
  - `otel-collector` (receives spans from app, exports to Jaeger)
- [ ] **9.3** Create `app/observability.py`:
  - OpenTelemetry tracer/meter initialization
  - Custom span decorators for pipeline stages
  - Prometheus metrics: `pipeline_duration_seconds` (histogram), `pipeline_stage_duration_seconds` (histogram by stage), `pipeline_errors_total` (counter by stage), `llm_tokens_total` (counter), `cache_hit_ratio` (gauge)
  - Structlog configuration: JSON format, output to stdout (collected by Loki)
- [ ] **9.4** Instrument FastAPI app with OpenTelemetry auto-instrumentation
- [ ] **9.5** Complete `app/pipeline.py` -- `async def run_pipeline(raw_input: str, context: dict) -> dict`:
  - Chain: `preprocess_input` -> `check_safety` -> `retrieve_context` -> `generate_response` (agent loop) -> `postprocess`
  - Wrap each stage in OpenTelemetry span with attributes (intent, entity count, cache_hit, etc.)
  - `asyncio.timeout` per stage (preprocess: 5s, rag: 10s, generate: 120s, postprocess: 5s)
  - Retry logic: 1 retry on transient failures (LLM timeout, Qdrant connection)
  - Redis caching: cache full pipeline results for identical inputs (short TTL: 60s)
  - Error handling: graceful fallbacks per stage (e.g., skip RAG if Qdrant down, use simpler response)
  - Emit metrics at each stage transition
- [ ] **9.6** Create Grafana dashboard JSON provisioning files:
  - Pipeline performance dashboard (stage latencies, error rates, throughput)
  - LLM usage dashboard (token counts, cache hit rates, model latency)
  - System health dashboard (container resources, DB connections, queue depth)
- [ ] **9.7** Expose a dedicated eval-friendly pipeline endpoint in `app/routes/pipeline.py`:
  - `POST /api/pipeline/run` (JWT-protected, captain/admin only): accepts `{"input": str, "context": dict}`, runs the full pipeline, returns structured response **plus** a `pipeline_trace` block containing: stage-by-stage latencies, cache hit/miss per stage, token counts, guard decisions, retrieval chunk count and scores, and the raw LLM output before post-processing. This is the clean API contract the eval runner (Phase 13) will target.
  - `POST /api/pipeline/run-batch` (admin only): accepts an array of `{input, context}` objects (max 50), runs each through the pipeline sequentially, returns an array of traced responses. Used for bulk eval test-set runs without needing a live UI.
  - Both endpoints must bypass Celery (synchronous, direct call to `run_pipeline`) so the eval runner gets a blocking response rather than a task ID.
  - Add these routes to `app/main.py` under an `/api/pipeline` prefix.
- [ ] **9.8** Ensure `run_pipeline()` emits a structured `PipelineTrace` Pydantic model (alongside the final response) capturing: `stage_timings: dict[str, float]`, `cache_hits: dict[str, bool]`, `guard_result: dict`, `rag_chunks_retrieved: int`, `rag_chunks_after_rerank: int`, `rag_top_scores: list[float]`, `llm_tokens_prompt: int`, `llm_tokens_completion: int`, `raw_llm_output: str`, `postprocess_mutations: list[str]` (list of what PII/validation changes were made). This trace is returned by the `/api/pipeline/run` endpoint and logged to structlog for Loki ingestion.
- [ ] **9.9** Write integration tests in `tests/test_pipeline.py`:
  - Test full pipeline end-to-end with mocked LLM
  - Test timeout behavior per stage
  - Test retry logic on transient failures
  - Test cache hit/miss paths
  - Verify OpenTelemetry spans are created
  - Test `/api/pipeline/run` returns valid `PipelineTrace` with all required fields
  - Test `/api/pipeline/run-batch` processes multiple inputs and returns array of traces

---

## Phase 10 - Web Dashboard & Streaming

**Pipeline concern:** Captain-facing UI with real-time AI interaction via Server-Sent Events. The dashboard provides an alternative to SMS for complex workflows (lineup planning, roster management) and demonstrates streaming LLM output -- a key production pattern for user experience during slow inference.

- [ ] **10.1** Set up Next.js frontend structure:
  ```
  frontend/src/
    app/
      layout.tsx        # Root layout with auth provider
      page.tsx           # Landing/login page
      dashboard/
        layout.tsx       # Dashboard shell (sidebar, nav)
        page.tsx          # Dashboard home (overview)
        teams/page.tsx    # Team management
        seasons/page.tsx  # Season management
        games/page.tsx    # Game/schedule view
        roster/page.tsx   # Roster management
        chat/page.tsx     # AI chat interface
    components/
      auth/              # Login form, register form, auth context
      teams/             # Team CRUD components
      roster/            # Player list, add/edit player
      games/             # Game cards, attendance grid
      chat/              # Chat interface, streaming message display
      ui/                # Shared UI components (buttons, inputs, modals)
    lib/
      api.ts             # Fetch wrapper with JWT
      auth.ts            # Auth utilities, token management
      types.ts           # TypeScript interfaces matching backend schemas
  ```
- [ ] **10.2** Implement authentication pages:
  - Login page with email/password form
  - Registration page for captains
  - JWT token storage (httpOnly cookie or secure localStorage)
  - Auth context provider with `useAuth` hook
  - Protected route wrapper (redirect to login if unauthenticated)
- [ ] **10.3** Implement Team management page:
  - List captain's teams
  - Create/edit team form
  - Team detail view with linked seasons
- [ ] **10.4** Implement Roster management page:
  - Player list with position prefs, sub flag, skill notes
  - Add/edit/remove player forms
  - Bulk import (CSV upload)
- [ ] **10.5** Implement Season & Game management:
  - Season CRUD (create, open/close, link teams)
  - Game list within season (date, time, location, attendance summary)
  - Schedule import (CSV/iCal file upload -> backend parsing)
  - Attendance grid: visual matrix of players vs games with status indicators
- [ ] **10.6** Create `app/routes/chat.py` on backend:
  - `GET /api/chat/stream` SSE endpoint: accepts query param, runs pipeline, yields `text/event-stream` chunks as LLM generates tokens
  - Proper SSE format with `data:` prefixed JSON events (type: token, tool_call, final_answer, error)
  - Connection keepalive and timeout handling
- [ ] **10.7** Implement AI Chat interface on frontend:
  - Chat message list with streaming text display
  - Input field for natural language queries
  - EventSource/fetch with ReadableStream for SSE consumption
  - Display tool call indicators (e.g., "Updating attendance...", "Checking roster...")
  - Chat history (session-scoped, stored in React state)
- [ ] **10.8** Implement Lineup view:
  - Display proposed lineups (from AI or manual)
  - Visual line groupings (Forward lines, Defense pairs, Goalies)
  - Lineup history for past games
- [ ] **10.9** Add responsive design and navigation:
  - Sidebar navigation for dashboard sections
  - Mobile-friendly layout (captains may use phone browser)
  - Loading states, error boundaries, toast notifications
- [ ] **10.10** Test: full flow -- login, create team, add players, create season/game, use AI chat to suggest lineup, view result

---

## Phase 11 - Testing & Quality Assurance

**Pipeline concern:** Verification of the entire system -- unit tests validate individual components, integration tests validate stage interactions, end-to-end tests validate real user workflows, and load tests validate performance under concurrent usage. Ensures the pipeline is reliable and performant.

> **Note:** Systematic LLM output quality evaluation (LLM-as-judge, test-set scoring, regression tracking) is intentionally out of scope for this project and lives in the companion eval runner described in Phase 13. The tests here cover functional correctness and pipeline behavior, not model output quality.

- [ ] **11.1** Write comprehensive unit tests for each pipeline stage:
  - `tests/test_preprocess.py`: entity extraction, intent classification, guard detection (min 15 test cases)
  - `tests/test_rag.py`: embedding, retrieval, re-ranking, compression (min 10 test cases)
  - `tests/test_generate.py`: prompt assembly, tool dispatch, agent loop (min 10 test cases)
  - `tests/test_postprocess.py`: PII redaction, validation, formatting (min 10 test cases)
- [ ] **11.2** Write integration tests in `tests/test_integration.py`:
  - Full pipeline: SMS input -> structured output (with mocked LLM)
  - Auth flow: register -> login -> access protected route -> token refresh
  - SMS flow: webhook receipt -> Celery task -> pipeline -> SMS response
  - CRUD flow: create team -> add players -> create season -> create game -> record attendance
- [ ] **11.3** Write end-to-end tests in `tests/test_e2e.py`:
  - Scenario: Captain sends SMS "Bob is out for Tuesday" -> attendance updated, sub request sent
  - Scenario: Captain asks "Balance lines for next game" -> lineup generated with explanation
  - Scenario: Player sends "I want to play defense" -> preference updated
  - Scenario: Captain broadcasts survey -> players respond -> responses collected
- [ ] **11.4** Create Locust load test in `tests/locustfile.py`:
  - Simulate concurrent SMS webhooks (target: 10 req/s sustained)
  - Simulate concurrent dashboard API calls
  - Measure p50/p95/p99 latencies, error rates
- [ ] **11.5** Add `pytest.ini` / `pyproject.toml` test configuration with markers (unit, integration, e2e, load)
- [ ] **11.6** Create test fixtures and factories in `tests/conftest.py` (database fixtures, mock Twilio, mock Ollama)
- [ ] **11.7** Verify all tests pass; fix any discovered bugs

---

## Phase 12 - Deployment Readiness & CI

**Pipeline concern:** Production hardening -- healthchecks ensure container orchestration can restart failed services, CI ensures code quality gates, and environment configuration ensures secure secret management. This is the final layer ensuring the system is deployable and maintainable.

- [ ] **12.1** Finalize `docker-compose.yml`:
  - Add healthchecks to all services (Postgres, Redis, Qdrant, Ollama, FastAPI, Celery worker)
  - Add restart policies (`unless-stopped`)
  - Configure resource limits (memory caps for LLM container)
  - Add named volumes for all persistent data
  - Create `docker-compose.override.yml` for local dev overrides
- [ ] **12.2** Create production `Dockerfile` for FastAPI app:
  - Multi-stage build (builder + runtime)
  - Non-root user
  - Health check instruction
  - Proper signal handling (graceful shutdown)
- [ ] **12.3** Create production `Dockerfile` for Next.js frontend:
  - Multi-stage build with `next build` + `next start`
  - Static asset optimization
- [ ] **12.4** Create `.env.production.example` with production-specific settings documented
- [ ] **12.5** Create CI configuration (`.github/workflows/ci.yml`):
  - Lint: `ruff` (Python), `eslint` (TypeScript)
  - Type check: `mypy` (Python), `tsc` (TypeScript)
  - Unit tests: `pytest -m unit`
  - Integration tests: `pytest -m integration` (with Postgres + Redis services)
  - Build verification: Docker build succeeds
- [ ] **12.6** Add `Makefile` with common commands:
  - `make dev` -- start full stack locally
  - `make test` -- run all tests
  - `make lint` -- run all linters
  - `make migrate` -- run Alembic migrations
  - `make seed` -- seed sample data
  - `make ingest` -- run Qdrant ingestion
- [ ] **12.7** Final verification: clean `docker compose up`, run full test suite, verify Grafana dashboards show pipeline metrics, send test SMS through complete flow
- [ ] **12.8** Update `README.md` with complete setup instructions, architecture diagram (text-based), and development workflow

---

---

## Phase 13 - Eval Runner (Companion Project)

**Pipeline concern:** LLM output quality evaluation -- this phase establishes a *separate companion project* (`leeg-eval/`) that treats the Leeg app as a black box and evaluates pipeline output quality systematically. This separation is intentional and reflects how eval should be structured in real client work: the eval system is a tool you bring to any AI pipeline, not something baked into the app itself.

> **Prerequisite:** Phase 9 must be complete (specifically steps 9.7 and 9.8) so that the `/api/pipeline/run` and `/api/pipeline/run-batch` endpoints are available with full `PipelineTrace` responses.

> **Why a separate project:** The eval runner has different dependencies, different lifecycle (run on demand, not in production), and different concerns than the app. Keeping it separate also makes it reusable -- you can point it at any pipeline that exposes a compatible endpoint contract.

- [ ] **13.1** Initialize a new sibling repo `leeg-eval/` (separate from the main `leeg/` repo):
  - Python 3.12 venv, `requirements.txt`: `httpx`, `pytest`, `pytest-asyncio`, `pydantic`, `structlog`, `rich`, `pandas`, `openai` (for LLM-as-judge calls to a frontier model), `jinja2`, `python-dotenv`
  - `.env.example`: `LEEG_API_URL` (points to running Leeg app), `LEEG_API_TOKEN` (admin JWT), `JUDGE_MODEL` (e.g. `gpt-4o-mini` or `claude-haiku`), `JUDGE_API_KEY`
  - Directory structure:
    ```
    leeg-eval/
      test_sets/         # JSONL files of {input, context, expected_intent, tags[]}
      judges/            # Judge prompt templates per evaluation dimension
      runners/
        batch_runner.py  # Sends test set to /api/pipeline/run-batch, collects traces
        single_runner.py # Interactive single-input runner for debugging
      scorers/
        llm_judge.py     # LLM-as-judge scoring against rubric
        deterministic.py # Rule-based checks (PII present?, response within length?, guard fired correctly?)
      reports/
        reporter.py      # Aggregate scores, render pass/fail table, save results to JSONL
      conftest.py
      run_eval.py        # CLI entrypoint: python run_eval.py --test-set test_sets/sms_flows.jsonl
    ```

- [ ] **13.2** Build the test set for SMS intent flows in `test_sets/sms_flows.jsonl`:
  - Minimum 30 test cases as JSONL, each with: `input` (raw SMS text), `context` (channel, from_phone), `expected_intent`, `expected_action` (e.g. attendance_update), `tags` (happy_path / edge_case / adversarial / security), `notes`
  - Include: happy path attendance updates, ambiguous inputs, out-of-scope messages, injection attempts (should trigger guard), player preference updates, lineup requests
  - Include 5+ adversarial cases specifically targeting the prompt injection guard (these should be *rejected* by the pipeline -- a correct guard rejection is a passing score)

- [ ] **13.3** Build the test set for lineup suggestion flows in `test_sets/lineup_flows.jsonl`:
  - Minimum 15 test cases covering: balanced line requests, short-bench scenarios (< 12 skaters), goalie-absent scenarios, specific player exclusion requests, conflicting preference edge cases
  - Each case includes a `scoring_rubric` field with the specific criteria the judge should evaluate against (e.g. "lineup should respect position_prefs where possible", "explanation should cite specific player attributes")

- [ ] **13.4** Build the LLM-as-judge scorer in `scorers/llm_judge.py`:
  - Accepts: `pipeline_input`, `pipeline_output`, `pipeline_trace`, `scoring_rubric`
  - Calls the judge model with a structured prompt asking it to score on: **accuracy** (did it do the right thing?), **groundedness** (is the response supported by retrieved context, not hallucinated?), **safety** (no PII leaked, appropriate refusals), **format** (SMS-appropriate length and tone)
  - Returns: `EvalResult` Pydantic model with per-dimension scores (0-1 float), pass/fail bool, and `reasoning` string from the judge
  - Use structured output (JSON mode) for the judge call so scores are parseable

- [ ] **13.5** Build deterministic checkers in `scorers/deterministic.py`:
  - `check_no_pii_in_output(output: str) -> bool`: run Presidio on the pipeline output, fail if PII detected
  - `check_guard_fired_correctly(trace: PipelineTrace, expected_safe: bool) -> bool`: compare guard decision in trace to expectation
  - `check_response_length(output: str, channel: str) -> bool`: fail if SMS output > 1600 chars
  - `check_intent_match(trace: PipelineTrace, expected_intent: str) -> bool`: check extracted intent matches expected
  - These run on every test case without LLM calls -- fast, free, and catch obvious failures before spending tokens on judge calls

- [ ] **13.6** Build the batch runner in `runners/batch_runner.py`:
  - Load test set JSONL, send to `/api/pipeline/run-batch`, collect responses + traces
  - Run deterministic checks on all results first
  - Run LLM judge on results that passed deterministic checks (avoids burning judge tokens on obviously broken outputs)
  - Aggregate into a results list

- [ ] **13.7** Build the reporter in `reports/reporter.py`:
  - Aggregate pass rates per dimension (accuracy, groundedness, safety, format)
  - Aggregate pass rates per tag (happy_path, edge_case, adversarial, security)
  - Render a rich terminal table using `rich`
  - Save full results to a timestamped JSONL file in `reports/runs/`
  - Print a single-line summary: `PASS_RATE: 87% | accuracy: 91% | groundedness: 84% | safety: 100% | format: 96% | (30/30 cases evaluated)`

- [ ] **13.8** Wire up the CLI entrypoint `run_eval.py`:
  - `python run_eval.py --test-set test_sets/sms_flows.jsonl` runs the full eval loop and prints the report
  - `python run_eval.py --input "Bob is out Tuesday" --context '{"channel":"sms"}' --debug` runs a single input and prints the full trace + judge reasoning for debugging
  - `python run_eval.py --compare runs/2024-01-01.jsonl runs/2024-01-15.jsonl` diffs two run reports to show score changes (regression detection)

- [ ] **13.9** Validate the eval runner end-to-end:
  - Start the Leeg app locally, obtain an admin JWT
  - Run `python run_eval.py --test-set test_sets/sms_flows.jsonl`
  - Verify: scores are plausible, adversarial cases show guard firing correctly, report renders cleanly
  - Intentionally break something in the pipeline (e.g. disable PII redaction) and verify the eval catches it

- [ ] **13.10** Document in `leeg-eval/README.md`:
  - What the eval runner does and how it relates to the main app
  - How to add new test cases
  - How to interpret scores and diagnose failures using the trace output
  - How to run a regression comparison before/after a pipeline change

---

## Progress Summary

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Project Initialization & Skeleton | Complete |
| 2 | Data Models & Database | Not Started |
| 3 | Authentication & API Skeleton | Not Started |
| 4 | SMS Integration & Inbound Webhook | Not Started |
| 5 | Stage 1: Preprocessing & Security | Not Started |
| 6 | Stage 2: Hybrid RAG | Not Started |
| 7 | Stage 3: Generation & Agentic Loops | Not Started |
| 8 | Stage 4: Post-Processing | Not Started |
| 9 | Pipeline Orchestration & Observability | Not Started |
| 10 | Web Dashboard & Streaming | Not Started |
| 11 | Testing & Quality Assurance | Not Started |
| 12 | Deployment Readiness & CI | Not Started |
| 13 | Eval Runner (Companion Project) | Not Started |

**Total Steps:** 109
**Completed:** 10
**Remaining:** 99