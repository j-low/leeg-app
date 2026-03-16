# FastAPI app factory, CORS middleware, and /health endpoint
# See CLAUDE.PROJECT.MD for full architecture

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import settings
from app.limiter import limiter
from app.observability import configure_observability, get_metrics_app
from app.routes import auth, chat, games, lineups, messaging, pipeline, players, seasons, sms, teams


def create_app() -> FastAPI:
    # Initialise structlog JSON + OTel before any request handling
    configure_observability(settings.otel_endpoint)

    app = FastAPI(
        title="Leeg",
        version="0.1.0",
        description="Rec-league hockey team management with AI pipeline",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # ── Rate limiting (slowapi) ───────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # ── CORS: allow Next.js dashboard to call the API ─────────────────────
    origins = settings.cors_origins_list()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # ── Security headers (XSS / MIME / frame protections for JSON API) ────
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response

    # ── OTel FastAPI auto-instrumentation ─────────────────────────────────
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass  # OTel not critical; fail silently if package missing

    # ── Prometheus /metrics endpoint ───────────────────────────────────────
    app.mount("/metrics", get_metrics_app())

    # ── Routers ───────────────────────────────────────────────────────────
    app.include_router(auth.router)
    app.include_router(teams.router)
    app.include_router(players.router)
    app.include_router(seasons.router)
    app.include_router(games.router)
    app.include_router(lineups.router)
    app.include_router(messaging.router)
    app.include_router(sms.router)
    app.include_router(pipeline.router)
    app.include_router(chat.router)

    @app.get("/health", tags=["meta"])
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
