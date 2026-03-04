"""
One-time / on-demand Qdrant ingestion script.

Reads all team data from Postgres and upserts embeddings into Qdrant.
Safe to re-run -- upsert is idempotent (same point ID = overwrite).

Usage:
    # Ingest all teams
    python scripts/ingest_to_qdrant.py

    # Ingest a specific team
    python scripts/ingest_to_qdrant.py --team-id 1
"""
import argparse
import asyncio
import sys
from pathlib import Path

# Ensure app package is importable from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.team import Team
from app.rag.ingestion import ingest_team_data


async def _ingest(team_id: int | None) -> None:
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        if team_id is not None:
            team_ids = [team_id]
        else:
            result = await db.execute(select(Team.id))
            team_ids = [row[0] for row in result.all()]

        if not team_ids:
            print("No teams found in database.")
            return

        total_upserted: dict[str, int] = {}
        for tid in team_ids:
            print(f"Ingesting team {tid} ...", end=" ", flush=True)
            summary = await ingest_team_data(tid, db)
            print(f"done: {summary}")
            for k, v in summary.items():
                total_upserted[k] = total_upserted.get(k, 0) + v

        print("\nIngestion complete.")
        print("Total documents upserted:")
        for doc_type, count in total_upserted.items():
            print(f"  {doc_type}: {count}")

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Postgres data into Qdrant.")
    parser.add_argument(
        "--team-id",
        type=int,
        default=None,
        help="Ingest a specific team (default: all teams)",
    )
    args = parser.parse_args()
    asyncio.run(_ingest(args.team_id))


if __name__ == "__main__":
    main()
