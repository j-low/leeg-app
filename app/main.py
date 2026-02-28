# FastAPI app factory, CORS middleware, and /health endpoint
# See CLAUDE.PROJECT.MD for full architecture

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Leeg",
        version="0.1.0",
        description="Rec-league hockey team management with AI pipeline",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # CORS: allow Next.js dashboard to call the API.
    # In production, restrict origins to the deployed frontend URL.
    origins = settings.cors_origins_list()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/health", tags=["meta"])
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
