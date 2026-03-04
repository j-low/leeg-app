"""
Celery application and async task definitions.

The worker is started separately from the FastAPI app:
    celery -A app.tasks.celery_app worker --loglevel=info

Broker:  Redis DB 1  (CELERY_BROKER_URL)
Backend: Redis DB 0  (REDIS_URL) -- stores task result metadata
"""
import asyncio

import structlog
from celery import Celery

from app.config import settings

log = structlog.get_logger(__name__)

celery_app = Celery(
    "leeg",
    broker=settings.celery_broker_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Retry failed tasks up to 3 times with exponential backoff
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)


@celery_app.task(
    name="leeg.process_inbound_sms",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def process_inbound_sms(self, from_phone: str, body: str) -> None:
    """Process an inbound SMS through the AI pipeline (Stages 1-4).

    Stages will be wired progressively in Phases 5-8.  Until then the
    pipeline stub raises NotImplementedError and we send a placeholder reply.
    """
    from app.pipeline import run_pipeline
    from app.sms import send_sms

    log.info("task.process_inbound_sms.start", from_phone=from_phone, body=body)

    try:
        result = asyncio.run(
            run_pipeline(
                raw_input=body,
                context={"channel": "sms", "from_phone": from_phone},
            )
        )
        response_text: str | None = result.get("response_text")
    except NotImplementedError:
        # Pipeline not yet wired (Phases 5-8 pending)
        log.info("task.process_inbound_sms.pipeline_stub", from_phone=from_phone)
        response_text = None
    except Exception as exc:
        log.error("task.process_inbound_sms.error", exc=str(exc))
        raise self.retry(exc=exc)

    if response_text:
        send_sms(to=from_phone, body=response_text)

    log.info("task.process_inbound_sms.done", from_phone=from_phone)


@celery_app.task(
    name="leeg.reingest_team_data",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def reingest_team_data(self, team_id: int) -> dict:
    """Re-embed and upsert a team's documents into Qdrant after a DB write.

    Called automatically after roster changes, game creation, or preference
    updates so the RAG vector store stays in sync with Postgres.

    Args:
        team_id: The team whose data should be re-ingested.

    Returns:
        Summary dict from ingest_team_data: {doc_type: count_upserted}.
    """
    from app.db import async_session
    from app.rag.ingestion import ingest_team_data

    log.info("task.reingest_team_data.start", team_id=team_id)

    async def _run() -> dict:
        async with async_session() as db:
            return await ingest_team_data(team_id, db)

    try:
        summary = asyncio.run(_run())
        log.info("task.reingest_team_data.done", team_id=team_id, summary=summary)
        return summary
    except Exception as exc:
        log.error("task.reingest_team_data.error", team_id=team_id, exc=str(exc))
        raise self.retry(exc=exc)
