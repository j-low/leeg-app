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

- [x] **2.1** Create SQLAlchemy ORM models in `app/models/`:
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
- [x] **2.2** Create `app/models/__init__.py` exporting `Base` and all models
- [x] **2.3** Create `app/db.py` with async SQLAlchemy engine, `AsyncSession` factory, `get_db` dependency
- [x] **2.4** Initialize Alembic: `alembic init migrations`; configure `alembic.ini` and `migrations/env.py` to use `app.config` and `app.models.Base.metadata`
- [x] **2.5** Generate and apply initial migration: `alembic revision --autogenerate -m "initial_tables"` && `alembic upgrade head`
- [x] **2.6** Create corresponding Pydantic schemas in `app/schemas/` for each entity (Create, Update, Read variants) with validation rules
- [x] **2.7** Write a seed script `scripts/seed_data.py` that inserts sample team, players, season, and game data for development
- [x] **2.8** Verify: run migration, execute seed script, query tables to confirm data integrity and relationships

---

## Phase 3 - Authentication & API Skeleton

**Pipeline concern:** Security boundary -- JWT auth protects dashboard/API routes, phone-based gating secures SMS endpoints. This is the first layer of defense-in-depth, ensuring only authorized users can trigger pipeline flows and access data.

- [x] **3.1** Add auth dependencies to `requirements.txt`: `python-jose[cryptography]`, `passlib[bcrypt]`, `python-multipart`
- [x] **3.2** Create `app/auth.py`: JWT token creation/validation utilities, password hashing, `get_current_user` dependency
- [x] **3.3** Create `app/models/user.py`: `User` table (id, email unique, hashed_password, phone, is_captain bool, is_active bool, created_at)
- [x] **3.4** Create `app/routes/auth.py`: endpoints for `POST /api/auth/register` (captain registration), `POST /api/auth/login` (returns JWT), `GET /api/auth/me` (current user info)
- [x] **3.5** Add Alembic migration for the User table
- [x] **3.6** Create CRUD API route stubs (protected by JWT) in `app/routes/`:
  - `teams.py`: CRUD for teams + roster management
  - `seasons.py`: CRUD for seasons, link/unlink teams
  - `games.py`: CRUD for games, attendance views
  - `lineups.py`: GET lineup history, POST request AI lineup suggestion
- [x] **3.7** Add rate limiting middleware using `slowapi` on all routes (stricter limits on auth endpoints)
- [x] **3.8** Add request validation and XSS protection middleware (sanitize inputs)
- [x] **3.9** Register all routers in `app/main.py` with appropriate prefixes and tags
- [x] **3.10** Test: register a captain, login, obtain JWT, access protected route, verify 401 on unauthenticated access

---

## Phase 4 - SMS Integration & Inbound Webhook

**Pipeline concern:** External interface -- Twilio provides the SMS channel that is the primary interaction mode. Webhook signature validation is a security concern; Celery async processing ensures the pipeline doesn't block on slow LLM inference, addressing latency and reliability.

- [x] **4.1** Add SMS dependencies to `requirements.txt`: `twilio`, `celery[redis]`
- [x] **4.2** Create `app/sms.py`: Twilio client wrapper (send_sms, send_group_sms), inbound signature validation utility
- [x] **4.3** Create `app/routes/sms.py`: `POST /sms/webhook` endpoint -- validate Twilio signature, extract `from_phone` and `body`, dispatch to Celery task, return TwiML acknowledgment
- [x] **4.4** Create `app/tasks.py`: Celery app configuration; `process_inbound_sms` task that calls `run_pipeline()` and sends response via Twilio
- [x] **4.5** Add `celery-worker` service to `docker-compose.yml` (uses Redis as broker)
- [x] **4.6** Create `app/routes/messaging.py`: captain-initiated endpoints for `POST /api/messages/send` (individual), `POST /api/messages/broadcast` (group), `POST /api/messages/survey` (survey blast)
- [x] **4.7** Add Twilio webhook URL configuration notes to `.env.example` and `README.md` (ngrok for local dev)
- [x] **4.8** Test: simulate inbound SMS via curl to webhook endpoint, verify Celery task queued and response sent (mock Twilio in tests)

---

## Phase 5 - Stage 1: Preprocessing & Security Guards

**Pipeline concern:** Input sanitization, entity extraction, intent classification, and prompt injection defense. This is the first AI pipeline stage -- it transforms raw natural language into structured data while enforcing security. Defense-in-depth: regex guards + Llama Guard + rate limiting form multiple security layers.

- [x] **5.1** Add NLP/security dependencies to `requirements.txt`: `spacy`, `transformers`, `torch` (or `llama-guard` client via Ollama)
- [x] **5.2** Download spaCy model: `python -m spacy download en_core_web_sm`
- [x] **5.3** Create `app/schemas/pipeline.py`: `StructuredInput` Pydantic model (raw_text, channel, from_phone, entities dict, intent str, is_safe bool, confidence float, metadata dict)
- [x] **5.4** Create `app/stages/preprocess.py` with `async def preprocess_input(raw_text: str, context: dict) -> StructuredInput`:
  - spaCy NER pipeline for PERSON, DATE, TIME, LOCATION extraction
  - Custom entity rules for hockey terms (positions: center/wing/defense/goalie, actions: attendance/lineup/preference/query/survey)
  - Intent classification heuristic (keyword + NER-based: attendance_update, lineup_request, preference_update, query, survey_response, sub_request, schedule_query)
  - Return `StructuredInput` with extracted data
- [x] **5.5** Create `app/stages/guards.py`:
  - Regex-based prompt injection detection (common injection patterns)
  - Llama Guard integration via Ollama for content safety classification
  - Combined `async def check_safety(text: str) -> tuple[bool, str]` returning (is_safe, reason)
- [x] **5.6** Integrate guards into `preprocess_input` -- reject with `SecurityError` if unsafe; log all rejections with structlog
- [x] **5.7** Write unit tests in `tests/test_preprocess.py`:
  - Test entity extraction on sample SMS messages ("Bob can't make it Tuesday", "I want to play wing")
  - Test intent classification accuracy
  - Test guard rejection of injection attempts ("ignore all instructions and...")
  - Test safe messages pass through

---

## Phase 6 - Stage 2: Hybrid RAG (Retrieval-Augmented Generation)

**Pipeline concern:** Grounding LLM responses in factual, team-specific data. Hybrid search (dense + sparse vectors) ensures recall; re-ranking improves precision; compression reduces token cost; Redis caching avoids redundant embedding/retrieval calls. This addresses hallucination prevention, cost control, and response quality.

- [x] **6.1** Add RAG dependencies to `requirements.txt`: `qdrant-client`, `sentence-transformers`, `langchain-text-splitters`, `llmlingua` (or `pyllmlingua`)
- [x] **6.2** Add `qdrant` service to `docker-compose.yml` (port 6333, with volume)
- [x] **6.3** Create `app/rag/embeddings.py`: embedding utility using `sentence-transformers` with `nomic-embed-text-v1.5` (or `all-MiniLM-L6-v2` as fallback). Batch embed function with Redis caching of embeddings
- [x] **6.4** Create `app/rag/ingestion.py`:
  - Chunk entities from Postgres into text documents (roster details, game history, player preferences, past lineups, survey responses)
  - Use `RecursiveCharacterTextSplitter` (chunk_size=512, overlap=50)
  - Embed and upsert to Qdrant collection `leeg_docs` with metadata filters (team_id, season_id, doc_type, last_updated)
  - Incremental upsert: track `last_updated` to avoid re-embedding unchanged data
- [x] **6.5** Create `app/rag/retriever.py`:
  - `async def retrieve(query: str, context: dict, top_k: int = 10) -> list[dict]`
  - Qdrant hybrid search (dense + sparse vectors with fusion)
  - Metadata filtering by team_id, season_id from context
  - Redis cache layer: cache query hash -> results with TTL
- [x] **6.6** Create `app/rag/reranker.py`: re-rank retrieved chunks using cross-encoder (`BAAI/bge-reranker-v2-m3` or lighter model); return top-k after re-ranking
- [x] **6.7** Create `app/stages/rag.py`:
  - `async def retrieve_context(structured_input: StructuredInput, context: dict) -> list[dict]`
  - Calls retriever, re-ranker, then applies LLMLingua compression to reduce token count
  - Returns compressed, relevant context chunks
- [x] **6.8** Write a one-time ingestion script `scripts/ingest_to_qdrant.py` that reads from Postgres and populates Qdrant
- [x] **6.9** Create Celery task for incremental re-ingestion triggered on DB writes (roster changes, new games, etc.)
- [x] **6.10** Write tests in `tests/test_rag.py`:
  - Test embedding generation and caching
  - Test ingestion pipeline (mock Qdrant)
  - Test retrieval with metadata filters
  - Test compression reduces token count

---

## Phase 7 - Stage 3: Generation, Tool Calling & Agentic Loops

**Pipeline concern:** Core LLM reasoning -- prompt engineering with structured output enforcement, tool-calling for real-world side effects (DB writes, SMS sends), and agentic ReAct loops for multi-step reasoning. Uses Claude Haiku via the Anthropic API (no self-hosted LLM required; no Docker service added). This is the heart of the AI pipeline.

- [x] **7.1** Add generation dependencies to `requirements.txt`: `anthropic`, `langgraph`, `instructor`, `jinja2`
- [x] **7.2** Add `ANTHROPIC_API_KEY` to `app/config.py` (`anthropic_api_key: str = ""`) and `.env.example`. No Docker service is needed -- Claude Haiku is called via the Anthropic API. In production, the key is stored in AWS SSM Parameter Store.
- [x] **7.3** Create `app/stages/prompts.py`: Jinja2 prompt templates for each intent type, producing `messages` lists compatible with the Anthropic API:
  - `base_system.j2`: shared role, constraints, and output format (included by all templates)
  - `attendance_update.j2`: system prompt + context + entities + attendance tool call instructions
  - `lineup_suggestion.j2`: system prompt + roster + preferences + criteria + structured output format
  - `general_query.j2`: system prompt + RAG context + question + answer format
  - `survey_collection.j2`: system prompt + survey context + response parsing instructions
- [x] **7.4** Create `app/stages/tools.py`: tool definitions in Claude tool use format (`name`, `description`, `input_schema`) paired with async Python implementations:
  - `update_attendance(game_id, player_id, status)` -> DB write
  - `get_attendance(game_id)` -> DB read
  - `send_sms(to_phone, message)` -> Twilio send
  - `send_group_sms(to_phones, message)` -> Twilio broadcast
  - `suggest_lineup(game_id, criteria)` -> generate lineup from roster/prefs
  - `get_roster(team_id)` -> DB read
  - `get_player_prefs(player_id)` -> DB read
  - `update_player_prefs(player_id, prefs)` -> DB write
  - `search_schedule(query)` -> DB read
- [x] **7.5** Create `app/stages/generate.py`:
  - `async def generate_response(structured_input: StructuredInput, rag_context: list[dict], context: dict) -> dict`
  - Render the appropriate Jinja2 template (system + user messages)
  - Call `anthropic.AsyncAnthropic` with `model="claude-haiku-4-5-20251001"`, `tools=[...]`, `tool_choice="auto"`
  - Parse response: `tool_use` blocks handed to agent loop; `text` blocks returned as final answer
- [x] **7.6** Create `app/stages/agent.py`: LangGraph ReAct agent loop:
  - State: `{messages, tool_results, iteration_count}`
  - Nodes: `call_llm`, `execute_tool`, `check_termination`
  - Maximum 5 iterations; 30s per-iteration timeout; 120s total timeout
  - On `stop_reason == "end_turn"` or max iterations: return final answer
- [x] **7.7** Write tests in `tests/test_generate.py`:
  - Test prompt assembly produces correct Anthropic message format
  - Test tool dispatch routes to correct Python function
  - Test agent loop terminates on `end_turn`
  - Test max iteration guard fires at iteration 5
  - Test structured output parsing from `tool_use` blocks (mock Anthropic client)

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
- [ ] **9.7** Expose eval-friendly pipeline endpoints in `app/routes/pipeline.py`. All endpoints are admin-only, bypass Celery (blocking direct calls), and return structured Pydantic responses the eval runner (Phase 13) can target. Add all routes to `app/main.py` under an `/api/pipeline` prefix.
  - **Full pipeline:**
    - `POST /api/pipeline/run`: accepts `{"input": str, "context": dict}`, runs all four stages, returns final response **plus** a `pipeline_trace` block (see step 9.8 for full trace schema). Primary eval runner target.
    - `POST /api/pipeline/run-batch`: accepts array of `{input, context}` objects (max 50), runs each sequentially, returns array of traced responses. Used for bulk test-set runs.
  - **Stage-isolated debug endpoints** (admin only, never used in the SMS path — eval and diagnostics only):
    - `POST /api/pipeline/debug/preprocess`: runs Stage 1 only. Accepts `{"input": str, "context": dict}`. Returns the full `StructuredInput` (intent, confidence, entities, guard result, `is_safe` flag). Enables retrieval-independent evaluation of intent classification and safety guard accuracy.
    - `POST /api/pipeline/debug/rag`: runs Stages 1–2. Accepts `{"input": str, "context": dict}`. Returns `StructuredInput` plus the full ranked chunk list with per-chunk scores, doc_type, entity_id, and compression flag. Enables descriptive and inferential statistics on retrieval quality (precision, recall, score distributions) without incurring LLM cost.
    - `POST /api/pipeline/debug/generate`: runs Stages 1–3. Accepts `{"input": str, "context": dict}` **or** `{"structured_input": StructuredInput, "rag_context": list[dict], "context": dict}` (the second form allows injecting a fixed/controlled RAG context for controlled generation experiments). Returns the raw agent loop result: `answer`, `tool_calls` log, `iterations`, `stop_reason`, and the full `messages` conversation history. Pre-post-processing. Enables generation quality evaluation with controlled inputs and analysis of tool call patterns.
- [ ] **9.8** Ensure `run_pipeline()` emits a structured `PipelineTrace` Pydantic model (alongside the final response) capturing: `stage_timings: dict[str, float]`, `cache_hits: dict[str, bool]`, `guard_result: dict`, `rag_chunks_retrieved: int`, `rag_chunks_after_rerank: int`, `rag_top_scores: list[float]`, `llm_tokens_prompt: int`, `llm_tokens_completion: int`, `raw_llm_output: str`, `postprocess_mutations: list[str]` (list of what PII/validation changes were made). This trace is returned by the `/api/pipeline/run` endpoint and logged to structlog for Loki ingestion.
- [ ] **9.9** Write integration tests in `tests/test_pipeline.py`:
  - Test full pipeline end-to-end with mocked LLM
  - Test timeout behavior per stage
  - Test retry logic on transient failures
  - Test cache hit/miss paths
  - Verify OpenTelemetry spans are created
  - Test `/api/pipeline/run` returns valid `PipelineTrace` with all required fields
  - Test `/api/pipeline/run-batch` processes multiple inputs and returns array of traces
  - Test `/api/pipeline/debug/preprocess` returns `StructuredInput` with correct intent and guard fields
  - Test `/api/pipeline/debug/rag` returns chunk list with scores; verify empty list on attendance intent
  - Test `/api/pipeline/debug/generate` with injected RAG context (controlled input form) returns agent result with `messages` history

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

## Phase 14 - Optimization Lab (Companion Project, extends leeg-eval/)

**Pipeline concern:** Systematic pipeline optimization -- this phase adds a structured experimentation layer to `leeg-eval/` that surveys every major optimization modality: prompt engineering, retrieval tuning, context management, guard calibration, and inference cost/performance tradeoffs. The core mechanic is a lightweight experiment tracker that tags each eval run with the parameter values that produced it, enabling before/after comparison and causal attribution of score changes.

> **Prerequisite:** Phase 13 must be complete. The optimization lab is built on top of the eval runner -- you optimize by running evals, changing a lever, and re-evaluating.

> **Design principle:** Each optimization modality is isolated. You change one family of parameters at a time, run the full test set, and compare. This is the same discipline as controlled experimentation in statistics -- you already think this way.

- [ ] **14.1** Add experiment tracking infrastructure to `leeg-eval/`:
  - Add dependencies to `requirements.txt`: `mlflow` (lightweight local experiment tracking)
  - Extend the directory structure:
    ```
    leeg-eval/
      experiments/
        configs/           # YAML files defining parameter variants per experiment
          prompt_variants/
          retrieval_variants/
          context_variants/
          guard_variants/
          inference_variants/
        results/           # MLflow tracking store (local)
      optimizers/
        experiment_runner.py  # Loads config, runs eval, logs params + metrics to MLflow
        comparator.py         # Compare two or more experiment runs, surface winning config
    ```
  - Initialize MLflow local tracking store: `mlflow.set_tracking_uri("experiments/results")`
  - Each experiment run logs: all parameter values as MLflow params, all eval scores as MLflow metrics, run timestamp and test set used as tags

- [ ] **14.2** Implement Experiment 1 — **Prompt Optimization**:
  - Create `experiments/configs/prompt_variants/` with 4 YAML configs varying:
    - System prompt verbosity (terse vs. detailed instructions)
    - Few-shot examples (0-shot vs. 3-shot with hockey-domain examples)
    - Output format instructions (explicit JSON schema in prompt vs. implicit)
    - Instruction ordering (role first vs. constraints first vs. examples first)
  - For each variant: the config specifies which prompt template file to use; `experiment_runner.py` swaps the template, runs the full SMS + lineup test sets, logs results
  - Expected learning: prompts are hyperparameters; instruction ordering and few-shot examples measurably affect accuracy and format scores
  - Document findings in `experiments/configs/prompt_variants/FINDINGS.md`: which variant won, by how much, and the hypothesis for why

- [ ] **14.3** Implement Experiment 2 — **Retrieval Optimization**:
  - Create `experiments/configs/retrieval_variants/` with configs varying:
    - Chunk size: 256 / 512 / 1024 tokens
    - Chunk overlap: 0 / 50 / 100 tokens
    - Top-k retrieved before reranking: 5 / 10 / 20
    - Reranking threshold: vary the score cutoff below which chunks are dropped
    - Hybrid search weight: dense-only / 70-30 dense-sparse / 50-50
  - Each variant requires re-ingesting to Qdrant with new chunk settings -- `experiment_runner.py` should call the ingestion script with the specified params before running eval
  - Track an additional metric per run: `avg_chunks_used` (from `PipelineTrace.rag_chunks_after_rerank`) -- this captures the cost/quality tradeoff directly
  - Expected learning: chunk size and top-k have the largest effect on groundedness; hybrid weighting matters more for ambiguous queries than precise ones
  - Document findings in `FINDINGS.md`

- [ ] **14.4** Implement Experiment 3 — **Context & Compression Optimization**:
  - Create `experiments/configs/context_variants/` with configs varying:
    - LLMLingua compression ratio: 0.5 / 0.7 / 0.9 (1.0 = no compression)
    - Context ordering: retrieved chunks in score order vs. reversed vs. most-relevant first and last (lost-in-the-middle mitigation)
    - Max context tokens passed to LLM: 512 / 1024 / 2048
  - Track additional metrics: `avg_prompt_tokens` and `avg_completion_tokens` from `PipelineTrace` -- this makes the cost/quality tradeoff visible as actual numbers
  - Expected learning: aggressive compression degrades groundedness measurably; context ordering has a real but smaller effect; the prompt token count is a direct cost proxy
  - Document findings in `FINDINGS.md`

- [ ] **14.5** Implement Experiment 4 — **Guard Calibration**:
  - Create `experiments/configs/guard_variants/` with configs varying:
    - Llama Guard sensitivity threshold (if configurable): strict / balanced / permissive
    - Regex rule set: minimal (obvious injections only) / standard / aggressive (broader patterns)
    - Guard ordering: regex-first-then-LLamaGuard (current) vs. LlamaGuard-only vs. regex-only
  - This experiment requires a dedicated test set: `test_sets/security_flows.jsonl` with minimum 20 cases -- 10 genuine injection attempts (should be rejected), 10 legitimate edge-case messages that could trigger false positives (should pass)
  - Track two competing metrics: `true_positive_rate` (injections correctly caught) and `false_positive_rate` (legitimate messages incorrectly rejected) -- the tension between these is the calibration problem
  - Expected learning: guard tuning is a precision/recall tradeoff, not a single dial; regex catches cheap obvious cases; LlamaGuard handles sophisticated attempts but adds latency
  - Document findings in `FINDINGS.md`

- [ ] **14.6** Implement Experiment 5 — **Inference Cost/Performance Optimization**:
  - Create `experiments/configs/inference_variants/` with configs varying:
    - Temperature: 0.0 / 0.3 / 0.7 (affects determinism and response variety)
    - Max tokens: 256 / 512 / 1024 (output length cap)
    - Quantization level: compare Q4 vs Q5 vs Q8 GGUF variants if available via Ollama
    - Redis cache TTL for full pipeline results: 30s / 60s / 300s
  - Track latency metrics from `PipelineTrace.stage_timings`: `p50_latency_ms`, `p95_latency_ms` per stage, total end-to-end
  - Track cost proxy: `total_tokens_per_run` = sum of all `llm_tokens_prompt + llm_tokens_completion` across test set
  - Expected learning: temperature 0.0 improves format consistency but can make lineup suggestions feel mechanical; Q4 vs Q5 quality delta is measurable on groundedness; cache TTL is a pure cost lever with no quality effect
  - Document findings in `FINDINGS.md`

- [ ] **14.7** Build the comparator in `optimizers/comparator.py`:
  - `python compare.py --experiments prompt_exp_1 prompt_exp_2 prompt_exp_3` queries MLflow for the named runs and renders a comparison table showing: each parameter value, each metric score, delta vs. baseline, and a winning configuration recommendation
  - `python compare.py --best --metric groundedness` queries all runs across all experiments and returns the single configuration with the highest groundedness score
  - `python compare.py --pareto --metrics groundedness,avg_prompt_tokens` renders a simple Pareto frontier: configurations that are not dominated on both quality and cost simultaneously
  - The Pareto command is the most important one to understand -- it surfaces the real optimization question, which is never "maximize quality" in isolation but "find the best quality achievable within a cost constraint"

- [ ] **14.8** Build a combined "best config" assembler:
  - After running all five experiment families, create `experiments/configs/optimized.yaml` that assembles the winning parameter from each experiment into a single combined configuration
  - Run a final eval pass with the combined config and compare to the original baseline config
  - Document the total score improvement and cost change in `experiments/OPTIMIZATION_SUMMARY.md`: a narrative of what you changed, what moved, and what the optimized pipeline looks like vs. the original
  - This document is the artifact you'd show a client or include in a portfolio -- it demonstrates not just that you built the pipeline but that you can systematically improve it

- [ ] **14.9** Extend the CLI in `run_eval.py` with optimization commands:
  - `python run_eval.py --experiment experiments/configs/prompt_variants/few_shot.yaml` runs a single experiment config and logs to MLflow
  - `python run_eval.py --run-all-experiments` runs every config in every `experiments/configs/` subdirectory sequentially and logs all results
  - `python run_eval.py --mlflow-ui` launches the MLflow local UI (`mlflow ui`) so results can be browsed visually -- this is the dashboard experience for the optimization workflow

- [ ] **14.10** Document in `leeg-eval/OPTIMIZATION.md`:
  - The five optimization modalities and what levers exist in each
  - How to add a new experiment config and what fields are required
  - How to interpret the MLflow UI and the comparator output
  - A decision tree for which modality to try first when eval scores are low (suggested order: prompt → retrieval → context → guard → inference)
  - A note on interaction effects: why you optimize one modality at a time and why the combined config in 14.8 may not be the simple sum of individual wins

---

## Phase 15 - Cloud Prep (AWS)

**Pipeline concern:** Production readiness before going live -- secrets management, TLS termination, nginx reverse proxy, and Twilio live webhook configuration. Deployment pattern: single EC2 VM running docker-compose (Option A -- straightforward, convertible to ECS Fargate later). All stateful services (Postgres, Redis, Qdrant) self-hosted in Docker containers on the same VM. Claude Haiku replaces any self-hosted LLM concern entirely.

- [ ] **15.1** Provision EC2 instance (Ubuntu 24.04 LTS, t3.small), create IAM user with least-privilege permissions, generate key pair, configure security group (inbound: SSH/22, HTTP/80, HTTPS/443 only)
- [ ] **15.2** Install Docker + docker-compose-plugin on EC2; allocate an Elastic IP; clone repo onto instance; copy production `.env` with real secret values
- [ ] **15.3** Register or reuse a domain; point its A record to the EC2 Elastic IP
- [ ] **15.4** Install nginx + certbot on EC2; configure reverse proxy: `https://<domain>` -> FastAPI port 8000 and Next.js port 3000 with Let's Encrypt TLS auto-renewal
- [ ] **15.5** Store all production secrets in AWS SSM Parameter Store (`/leeg/prod/*`); write `scripts/fetch_secrets.sh` that pulls them into `.env` on each deploy
- [ ] **15.6** Add `ANTHROPIC_API_KEY` to SSM (`/leeg/prod/anthropic_api_key`); verify it is correctly read by the app at startup
- [ ] **15.7** Update Twilio webhook URL in the Twilio console to `https://<domain>/sms/webhook`; send a test SMS and verify signature validation passes end-to-end
- [ ] **15.8** Create `docker-compose.prod.yml` override: remove host port exposure (traffic flows through nginx only), add memory limits, configure Docker log driver (awslogs or json-file with rotation)

---

## Phase 16 - Cloud Deployment & Smoke Test

**Pipeline concern:** End-to-end verification that the full system works in production -- database migrations, Qdrant data ingestion, live SMS pipeline, and dashboard accessible over HTTPS. Establishes the production runbook.

- [ ] **16.1** Run `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d` on EC2; verify all containers reach healthy status
- [ ] **16.2** Run Alembic migrations against production Postgres: `alembic upgrade head`
- [ ] **16.3** Run `python scripts/ingest_to_qdrant.py` against production Qdrant to populate vector store with real team data
- [ ] **16.4** Smoke test API layer: `/health` returns 200, captain registration + login succeed, JWT-protected route returns 200
- [ ] **16.5** Smoke test SMS pipeline: send a real SMS to the Twilio number, verify Celery task runs, verify AI response is received
- [ ] **16.6** Smoke test dashboard: open `https://<domain>` in browser, complete login flow, submit an AI chat query, verify streamed response
- [ ] **16.7** Configure a basic CloudWatch alarm: EC2 CPU > 80% for 5 minutes and disk utilisation > 85% trigger email alert
- [ ] **16.8** Document production runbook in `README.md`: how to deploy, roll back, rotate secrets, tail logs, and re-run ingestion

---

## Progress Summary

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Project Initialization & Skeleton | Complete |
| 2 | Data Models & Database | Complete |
| 3 | Authentication & API Skeleton | Complete |
| 4 | SMS Integration & Inbound Webhook | Complete |
| 5 | Stage 1: Preprocessing & Security | Complete |
| 6 | Stage 2: Hybrid RAG | Complete |
| 7 | Stage 3: Generation & Agentic Loops | Complete |
| 8 | Stage 4: Post-Processing | Not Started |
| 9 | Pipeline Orchestration & Observability | Not Started |
| 10 | Web Dashboard & Streaming | Not Started |
| 11 | Testing & Quality Assurance | Not Started |
| 12 | Deployment Readiness & CI | Not Started |
| 13 | Eval Runner (Companion Project) | Not Started |
| 14 | Optimization Lab (Companion Project) | Not Started |
| 15 | Cloud Prep (AWS EC2 + nginx + SSM) | Not Started |
| 16 | Cloud Deployment & Smoke Test | Not Started |

**Total Steps:** 137
**Completed:** 60
**Remaining:** 77