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

- [x] **8.1** Add post-processing dependencies to `requirements.txt`: `presidio-analyzer>=2.2,<3.0`, `presidio-anonymizer>=2.2,<3.0` (reuse existing spacy `en_core_web_sm`)
- [x] **8.2** Add `PostprocessedResponse` Pydantic model to `app/schemas/pipeline.py` (alongside `StructuredInput`); fields: `text_for_user`, `channel`, `mutations`, `pii_detected`, `was_truncated`, `tool_calls`, `iterations`, `stop_reason`, `dashboard_payload`
- [x] **8.3** Create `app/stages/postprocess/pii.py`:
  - Module-level singletons: `_analyzer` (AnalyzerEngine) and `_anonymizer` (AnonymizerEngine) built once at import via `_build_analyzer()` (same singleton pattern as `_build_nlp()` in preprocess)
  - `async def redact_pii(text, extra_names) -> tuple[str, bool]` — wraps sync Presidio calls in `asyncio.to_thread()`; fail-open on any exception
  - Standard entities: `PHONE_NUMBER`, `EMAIL_ADDRESS`, `PERSON`
  - Custom `_HockeyCaptainNoteRecognizer(PatternRecognizer)` catches leaked captain note patterns as defense-in-depth
  - `extra_names` param: word-boundary regex replacement for roster-aware player name suppression
- [x] **8.4** Create `app/stages/postprocess/formatter.py`:
  - `format_for_sms(text) -> tuple[str, bool]`: GSM-7 normalization (curly quotes/em-dashes → ASCII), soft limit 160 chars, hard limit 1600 chars (truncate via `textwrap.shorten`)
  - `format_for_dashboard(text, raw_output) -> tuple[str, dict]`: no length limit; returns structured `dashboard_payload` with `answer`, `tool_calls`, `iterations`, `stop_reason`
- [x] **8.5** Create `app/stages/postprocess/postprocess.py` — orchestrator: validate → redact PII → format (SMS or dashboard) → structlog audit log → return `PostprocessedResponse`; entire body wrapped in `try/except`, never raises; never logs `text_for_user` in full (only `output_len`)
- [x] **8.6** Create `app/stages/postprocess/__init__.py` with re-exports: `postprocess`, `PostprocessedResponse`, `redact_pii`, `format_for_sms`, `format_for_dashboard`, `SMS_SOFT_LIMIT`, `SMS_HARD_LIMIT`
- [x] **8.7** Write tests in `tests/test_postprocess.py` (15 tests, 3 classes, all Presidio mocked):
  - `TestPiiRedaction` (5): phone/email redacted, clean text passes through, extra_names suppression, Presidio exception fails open
  - `TestFormatter` (4): short SMS unchanged, >1600 truncated, smart quotes normalized, dashboard payload structure
  - `TestPostprocess` (6): happy path SMS/dashboard, PII detected, empty answer fallback, exception fallback, audit log emitted

---

## Phase 9 - Pipeline Orchestration & Observability

**Pipeline concern:** End-to-end pipeline wiring, async flow control, caching strategy, and full observability stack (traces, metrics, logs). This is where individual stages become a production system -- with timeouts, retries, circuit breakers, and the ability to diagnose issues via distributed tracing and dashboards.

- [x] **9.1** Add observability dependencies to `requirements.txt`: `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp`, `opentelemetry-instrumentation-fastapi`, `prometheus-client`, `python-json-logger`
- [x] **9.2** Add observability services to `docker-compose.yml`:
  - `prometheus` (port 9090, with config to scrape FastAPI metrics)
  - `grafana` (port 3001 — 3000 reserved for Next.js Phase 10, with provisioned datasources for Prometheus + Loki + Jaeger)
  - `loki` (port 3100, log aggregation)
  - `jaeger` (port 16686, distributed tracing UI)
  - `otel-collector` (receives spans from app, exports to Jaeger)
  - `promtail` (ships container logs → Loki)
- [x] **9.3** Create `app/observability.py`:
  - OpenTelemetry tracer/meter initialization
  - Custom span decorators for pipeline stages
  - Prometheus metrics: `pipeline_duration_seconds` (histogram), `pipeline_stage_duration_seconds` (histogram by stage), `pipeline_errors_total` (counter by stage), `llm_tokens_total` (counter)
  - Structlog configuration: JSON format, output to stdout (collected by Loki)
- [x] **9.4** Instrument FastAPI app with OpenTelemetry auto-instrumentation
- [x] **9.5** Complete `app/pipeline.py` with channel-aware dual-mode execution. Channel (`"sms"` or `"dashboard"`) is read from `context["channel"]` and determines which execution path is taken. **Eval always uses the batch path.**
  - **Batch path** — `async def run_pipeline(raw_input: str, context: dict) -> PostprocessedResponse`:
    - Used by: SMS inbound webhook, `/api/pipeline/run` eval endpoint
    - Chain: `preprocess` → `retrieve_context` → `run_agent()` → `postprocess()`
    - `asyncio.timeout` per stage (preprocess: 5s, rag: 10s, generate: 120s, postprocess: 5s)
    - Retry logic: 1 retry on transient LLM/Qdrant failures
    - Redis caching: cache full pipeline result for identical inputs (TTL: 60s)
    - Returns complete `PostprocessedResponse` (PII-redacted, formatted)
    - Wrap each stage in OpenTelemetry span; emit Prometheus metrics at each stage transition
  - **Streaming path** — `async def run_pipeline_stream(raw_input: str, context: dict) -> AsyncGenerator[dict, None]`:
    - Used by: dashboard SSE endpoint (`POST /api/chat/stream`) only
    - Stages 1–2 run identically to batch (preprocess + RAG); no caching on the stream path
    - Stage 3 uses `stream_agent()` (see 9.5a) instead of `run_agent()` — yields typed SSE event dicts as they arrive
    - Stage 4 deferred: PII redaction applied to the fully-accumulated answer text; emitted as a final `{type: "done", text_for_user: str, mutations: list}` event before the generator closes
    - Error events: `{type: "error", message: str}` — never raises, mirrors batch path's fail-safe design
- [x] **9.5a** Add `stream_agent()` to `app/stages/generation/agent.py`:
  - Uses `client.messages.stream()` (Anthropic async streaming context manager) instead of `client.messages.create()`
  - Yields typed event dicts at each meaningful point in the agent loop:
    - `{type: "thinking", text: str}` — streamed text tokens as they arrive
    - `{type: "tool_start", name: str, input: dict}` — tool call dispatched
    - `{type: "tool_result", name: str, result: str}` — tool execution complete
    - `{type: "answer_token", text: str}` — final answer streaming tokens
  - Same max-iteration guard and timeout logic as `run_agent()`; on hitting limit, yields `{type: "answer_token", text: fallback}` and closes
- [x] **9.6** Create Grafana dashboard JSON provisioning files:
  - Pipeline performance dashboard (stage latencies, error rates, throughput)
  - LLM usage dashboard (token counts, cache hit rates, model latency)
  - System health dashboard (container resources, DB connections, queue depth)
- [x] **9.7** Expose eval-friendly pipeline endpoints in `app/routes/pipeline.py`. All endpoints are admin-only, bypass Celery (blocking direct calls), and return structured Pydantic responses the eval runner (Phase 13) can target. Add all routes to `app/main.py` under an `/api/pipeline` prefix.
  - **Full pipeline:**
    - `POST /api/pipeline/run`: accepts `{"input": str, "context": dict}`, runs all four stages, returns final response **plus** a `pipeline_trace` block (see step 9.8 for full trace schema). Primary eval runner target.
    - `POST /api/pipeline/run-batch`: accepts array of `{input, context}` objects (max 50), runs each sequentially, returns array of traced responses. Used for bulk test-set runs.
  - **Stage-isolated debug endpoints** (admin only, never used in the SMS path — eval and diagnostics only):
    - `POST /api/pipeline/debug/preprocess`: runs Stage 1 only. Accepts `{"input": str, "context": dict}`. Returns the full `StructuredInput` (intent, confidence, entities, guard result, `is_safe` flag). Enables retrieval-independent evaluation of intent classification and safety guard accuracy.
    - `POST /api/pipeline/debug/rag`: runs Stages 1–2. Accepts `{"input": str, "context": dict}`. Returns `StructuredInput` plus the full ranked chunk list with per-chunk scores, doc_type, entity_id, and compression flag. Enables descriptive and inferential statistics on retrieval quality (precision, recall, score distributions) without incurring LLM cost.
    - `POST /api/pipeline/debug/generate`: runs Stages 1–3. Accepts `{"input": str, "context": dict}` **or** `{"structured_input": StructuredInput, "rag_context": list[dict], "context": dict}` (the second form allows injecting a fixed/controlled RAG context for controlled generation experiments). Returns the raw agent loop result: `answer`, `tool_calls` log, `iterations`, `stop_reason`, and the full `messages` conversation history. Pre-post-processing. Enables generation quality evaluation with controlled inputs and analysis of tool call patterns.
- [x] **9.8** Ensure `run_pipeline()` emits a structured `PipelineTrace` Pydantic model (alongside the final response) capturing: `stage_timings: dict[str, float]`, `cache_hits: dict[str, bool]`, `guard_result: dict`, `rag_chunks_retrieved: int`, `rag_chunks_after_rerank: int`, `rag_top_scores: list[float]`, `llm_tokens_prompt: int`, `llm_tokens_completion: int`, `raw_llm_output: str`, `postprocess_mutations: list[str]` (list of what PII/validation changes were made). This trace is returned by the `/api/pipeline/run` endpoint and logged to structlog for Loki ingestion.
- [x] **9.9** Write integration tests in `tests/test_pipeline.py` (all external calls mocked — no running services):
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
  - **Channel branching tests** (confirm the correct execution path is taken based on `context["channel"]`):
    - SMS input (`channel="sms"`) → `run_pipeline()` called, returns `PostprocessedResponse`; `run_pipeline_stream()` never called
    - Dashboard input (`channel="dashboard"`) → `run_pipeline_stream()` called, `run_pipeline()` never called
    - `run_pipeline_stream()` with mocked `stream_agent()` yields events in order: one or more `thinking`/`tool_start`/`tool_result` events followed by `answer_token` events, closed by exactly one `done` event
    - `done` event contains PII-redacted `text_for_user` and `mutations` list (confirms post-processing applied at stream close)
    - `error` event yielded (not exception raised) when a stage fails mid-stream
    - `POST /api/chat/stream` route: returns `Content-Type: text/event-stream`, each line is valid `data: <json>` SSE format, connection closed after `done` event

---

## Phase 10 - Web Dashboard & Streaming

**Pipeline concern:** Captain-facing UI with real-time AI interaction via Server-Sent Events. The dashboard provides an alternative to SMS for complex workflows (lineup planning, roster management) and demonstrates streaming LLM output -- a key production pattern for user experience during slow inference.

- [x] **10.1** Set up Next.js frontend structure:
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
- [x] **10.2** Implement authentication pages:
  - Login page with email/password form
  - Registration page for captains
  - JWT token storage (httpOnly cookie or secure localStorage)
  - Auth context provider with `useAuth` hook
  - Protected route wrapper (redirect to login if unauthenticated)
- [x] **10.3** Implement Team management page:
  - List captain's teams
  - Create/edit team form
  - Team detail view with linked seasons
- [x] **10.4** Implement Roster management page:
  - Player list with position prefs, sub flag, skill notes
  - Add/edit/remove player forms
  - Bulk import (CSV upload)
- [x] **10.5** Implement Season & Game management:
  - Season CRUD (create, open/close, link teams)
  - Game list within season (date, time, location, attendance summary)
  - Schedule import (CSV/iCal file upload -> backend parsing)
  - Attendance grid: visual matrix of players vs games with status indicators
- [x] **10.6** Create `app/routes/chat.py` on backend:
  - `POST /api/chat/stream`: JWT-authenticated SSE endpoint for dashboard channel only
  - Accepts `{"input": str, "context": dict}` — sets `context["channel"] = "dashboard"` and delegates to `run_pipeline_stream()` (Phase 9.5)
  - Serializes each yielded event dict to `data: <json>\n\n` SSE format; flushes immediately
  - Event types (defined by `run_pipeline_stream()`): `thinking`, `tool_start`, `tool_result`, `answer_token`, `done`, `error`
  - Connection keepalive: yield `data: {"type": "ping"}\n\n` every 15s if no events
  - Client disconnect detection: wrap generator in try/finally; cancel pipeline task on disconnect
- [x] **10.7** Implement AI Chat interface on frontend:
  - Chat message list with streaming text display
  - Input field for natural language queries
  - EventSource/fetch with ReadableStream for SSE consumption
  - Display tool call indicators (e.g., "Updating attendance...", "Checking roster...")
  - Chat history (session-scoped, stored in React state)
- [x] **10.8** Implement Lineup view:
  - Display proposed lineups (from AI or manual)
  - Visual line groupings (Forward lines, Defense pairs, Goalies)
  - Lineup history for past games
- [x] **10.9** Add responsive design and navigation:
  - Sidebar navigation for dashboard sections
  - Mobile-friendly layout (captains may use phone browser)
  - Loading states, error boundaries, toast notifications
- [ ] **10.10** Test: full flow -- login, create team, add players, create season/game, use AI chat to suggest lineup, view result

---

## Phase 11 - Testing & Quality Assurance

**Pipeline concern:** Verification of the entire system -- unit tests validate individual components, integration tests validate stage interactions, end-to-end tests validate real user workflows, and load tests validate performance under concurrent usage. Ensures the pipeline is reliable and performant.

> **Note:** Systematic LLM output quality evaluation (LLM-as-judge, test-set scoring, regression tracking) is intentionally out of scope for this project and lives in the companion eval runner described in Phase 13. The tests here cover functional correctness and pipeline behavior, not model output quality.

- [x] **11.1** Write comprehensive unit tests for each pipeline stage:
  - `tests/test_preprocess.py`: entity extraction, intent classification, guard detection (min 15 test cases)
  - `tests/test_rag.py`: embedding, retrieval, re-ranking, compression (min 10 test cases)
  - `tests/test_generate.py`: prompt assembly, tool dispatch, agent loop (min 10 test cases)
  - `tests/test_postprocess.py`: PII redaction, validation, formatting (min 10 test cases)
- [x] **11.2** Write integration tests in `tests/test_integration.py`:
  - Full pipeline: SMS input -> structured output (with mocked LLM)
  - Auth flow: register -> login -> access protected route -> token refresh
  - SMS flow: webhook receipt -> Celery task -> pipeline -> SMS response
  - CRUD flow: create team -> add players -> create season -> create game -> record attendance
- [x] **11.3** Write end-to-end tests in `tests/test_e2e.py`:
  - Scenario: Captain sends SMS "Bob is out for Tuesday" -> attendance updated, sub request sent
  - Scenario: Captain asks "Balance lines for next game" -> lineup generated with explanation
  - Scenario: Player sends "I want to play defense" -> preference updated
  - Scenario: Captain broadcasts survey -> players respond -> responses collected
- [x] **11.4** Create Locust load test in `tests/locustfile.py`:
  - Simulate concurrent SMS webhooks (target: 10 req/s sustained)
  - Simulate concurrent dashboard API calls
  - Measure p50/p95/p99 latencies, error rates
- [x] **11.5** Add `pytest.ini` / `pyproject.toml` test configuration with markers (unit, integration, e2e, load)
- [x] **11.6** Create test fixtures and factories in `tests/conftest.py` (database fixtures, mock Twilio, mock Ollama)
- [ ] **11.7** Verify all tests pass; fix any discovered bugs

---

## Phase 12 - Deployment Readiness & CI

**Pipeline concern:** Production hardening -- healthchecks ensure container orchestration can restart failed services, CI ensures code quality gates, and environment configuration ensures secure secret management. This is the final layer ensuring the system is deployable and maintainable.

- [x] **12.1** Finalize `docker-compose.yml`:
  - Add healthchecks to all services (Postgres, Redis, Qdrant, FastAPI)
  - Add restart policies (`unless-stopped`)
  - Configure resource limits (CPU/memory caps per service)
  - Add named volumes for all persistent data
  - Create `docker-compose.override.yml` for local dev overrides (hot-reload bind mounts)
- [x] **12.2** Create production `Dockerfile` for FastAPI app:
  - 3-stage multi-stage build (base → deps → runtime)
  - Non-root user (`appuser`)
  - Health check instruction (`curl /health`)
  - 2-worker uvicorn in production
- [x] **12.3** Create production `Dockerfile` for Next.js frontend:
  - 3-stage multi-stage build (deps → builder → runner)
  - `output: "standalone"` in `next.config.ts` for minimal image
  - Non-root user (`nextjs`)
- [x] **12.4** Create `.env.production.example` with production-specific settings documented
- [x] **12.5** Create CI configuration (`.github/workflows/ci.yml`):
  - Lint: `ruff` (Python), `eslint` (TypeScript)
  - Type check: `mypy` (Python), `tsc` (TypeScript)
  - Tests: `pytest -m "unit or integration or e2e"` with coverage upload
  - Build verification: both Docker images build successfully
- [x] **12.6** Add `Makefile` with common commands:
  - `make dev` -- start full stack locally
  - `make test` / `make test-unit` / `make test-integration` / `make test-e2e`
  - `make lint` / `make typecheck` -- ruff + eslint, mypy + tsc
  - `make migrate` / `make seed` / `make ingest`
  - `make load-test` -- Locust load test
- [ ] **12.7** Final verification: clean `docker compose up`, run full test suite, verify Grafana dashboards show pipeline metrics, send test SMS through complete flow
- [x] **12.8** Update `README.md` with complete setup instructions, architecture diagram (text-based), and development workflow

---

---

## Phase 13 - Eval Runner (Companion Project) ⟶ leeg-eval

> **Moved.** This phase is tracked in full in the `leeg-eval` companion project. See [leeg-eval/PROJECT_CHECKLIST.md](../leeg-eval/PROJECT_CHECKLIST.md) — Phases 1–5 cover the complete eval runner: project initialization, test set construction, scoring layer (LLM-as-judge + deterministic checkers), batch runner, reporting, and CLI.

> **Prerequisite from this project:** Steps 9.7 and 9.8 must be complete so that `/api/pipeline/run` and `/api/pipeline/run-batch` return full `PipelineTrace` responses.

| leeg-app step | leeg-eval equivalent |
|---------------|----------------------|
| 13.1 — Initialize leeg-eval repo | [Phase 1](../leeg-eval/PROJECT_CHECKLIST.md) — Project Initialization & Structure |
| 13.2–13.3 — Build test sets | [Phase 2](../leeg-eval/PROJECT_CHECKLIST.md) — Test Set Construction |
| 13.4–13.5 — Build scorers | [Phase 3](../leeg-eval/PROJECT_CHECKLIST.md) — Scoring Layer |
| 13.6 — Build batch runner | [Phase 4](../leeg-eval/PROJECT_CHECKLIST.md) — Runner & Batch Infrastructure |
| 13.7–13.10 — Reporting, CLI, validation | [Phase 5](../leeg-eval/PROJECT_CHECKLIST.md) — Reporting, CLI & Validation |

---

## Phase 14 - Optimization Lab (Companion Project, extends leeg-eval/) ⟶ leeg-eval

> **Moved.** This phase is tracked in full in the `leeg-eval` companion project. See [leeg-eval/PROJECT_CHECKLIST.md](../leeg-eval/PROJECT_CHECKLIST.md) — Phases 6–13 cover the complete optimization lab: MLflow experiment tracking infrastructure, five experiment families (prompt, retrieval, context/compression, guard calibration, inference cost/performance), the Pareto-frontier comparator, combined best-config synthesis, CI, and the Makefile.

> **Prerequisite from this project:** Phase 13 (leeg-eval Phases 1–5) must be complete before starting the optimization lab.

| leeg-app step | leeg-eval equivalent |
|---------------|----------------------|
| 14.1 — MLflow infrastructure | [Phase 6](../leeg-eval/PROJECT_CHECKLIST.md) — Experiment Tracking Infrastructure |
| 14.2 — Prompt optimization | [Phase 7](../leeg-eval/PROJECT_CHECKLIST.md) — Experiment: Prompt Optimization |
| 14.3 — Retrieval optimization | [Phase 8](../leeg-eval/PROJECT_CHECKLIST.md) — Experiment: Retrieval Optimization |
| 14.4 — Context/compression optimization | [Phase 9](../leeg-eval/PROJECT_CHECKLIST.md) — Experiment: Context & Compression Optimization |
| 14.5 — Guard calibration | [Phase 10](../leeg-eval/PROJECT_CHECKLIST.md) — Experiment: Guard Calibration |
| 14.6 — Inference cost/performance | [Phase 11](../leeg-eval/PROJECT_CHECKLIST.md) — Experiment: Inference Cost & Performance |
| 14.7–14.9 — Comparator, best config, CLI | [Phase 12](../leeg-eval/PROJECT_CHECKLIST.md) — Comparator & Optimization Synthesis |
| 14.10 — Documentation | [Phase 13](../leeg-eval/PROJECT_CHECKLIST.md) — CI & Operational Tooling |

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
| 8 | Stage 4: Post-Processing | Complete |
| 9 | Pipeline Orchestration & Observability | Complete |
| 10 | Web Dashboard & Streaming | Not Started |
| 11 | Testing & Quality Assurance | Not Started |
| 12 | Deployment Readiness & CI | Not Started |
| 13 | Eval Runner (Companion Project) | Not Started |
| 14 | Optimization Lab (Companion Project) | Not Started |
| 15 | Cloud Prep (AWS EC2 + nginx + SSM) | Not Started |
| 16 | Cloud Deployment & Smoke Test | Not Started |

**Total Steps:** 137
**Completed:** 79
**Remaining:** 58