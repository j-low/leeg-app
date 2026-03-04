"""
RAG Stage 2: Document ingestion from Postgres -> Qdrant.

Reads team data (players, games, preferences, survey responses) from
Postgres, formats each record as a natural-language text document, chunks
long texts, embeds them, and upserts into the Qdrant collection 'leeg_docs'.

Incremental upsert:
  Point ID = sha256(team_id:doc_type:entity_id:chunk_idx), deterministic so
  re-runs on unchanged data are no-ops.

All ML/vector-DB imports (qdrant_client, langchain_text_splitters) are lazy
so this module is importable without those packages installed.
"""
import hashlib
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.game import Game
from app.models.player import Player
from app.models.player_preference import PlayerPreference
from app.models.survey import SurveyResponse
from app.rag.embeddings import embed_texts

log = logging.getLogger(__name__)

COLLECTION_NAME = "leeg_docs"
VECTOR_SIZE = 384         # all-MiniLM-L6-v2 output dimension
CHUNK_SIZE = 512
CHUNK_OVERLAP = 50


def _get_splitter():
    from langchain_text_splitters import RecursiveCharacterTextSplitter  # lazy
    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
    )


def _get_qdrant():
    from qdrant_client import AsyncQdrantClient  # lazy
    return AsyncQdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


# ── Collection bootstrap ──────────────────────────────────────────────────────

async def ensure_collection(client) -> None:
    """Create 'leeg_docs' collection if it doesn't exist."""
    from qdrant_client.models import Distance, VectorParams  # lazy
    existing = {c.name for c in (await client.get_collections()).collections}
    if COLLECTION_NAME not in existing:
        await client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        log.info("ingestion.collection_created name=%s", COLLECTION_NAME)


# ── Document formatters ───────────────────────────────────────────────────────

def _fmt_player(player: Player) -> str:
    parts = [f"Player: {player.name}"]
    if player.position_prefs:
        parts.append(f"Position preferences: {', '.join(player.position_prefs)}")
    if player.skill_notes:
        parts.append(f"Skill notes: {player.skill_notes}")
    if player.sub_flag:
        parts.append("Available as substitute: yes")
    return ". ".join(parts) + "."


def _fmt_game(game: Game) -> str:
    parts = [f"Game on {game.game_date}"]
    if game.game_time:
        parts.append(f"at {game.game_time}")
    if game.location:
        parts.append(f"at {game.location}")
    if game.notes:
        parts.append(f"Notes: {game.notes}")
    return " ".join(parts) + "."


def _fmt_preference(pref: PlayerPreference, player_name: str) -> str:
    parts = [f"Player preferences for {player_name}"]
    if pref.position_prefs:
        parts.append(f"preferred positions: {', '.join(pref.position_prefs)}")
    if pref.ice_time_constraints:
        parts.append(f"ice time constraints: {pref.ice_time_constraints}")
    if pref.style_notes:
        parts.append(f"style notes: {pref.style_notes}")
    return ". ".join(parts) + "."


def _fmt_survey(resp: SurveyResponse, player_name: str) -> str:
    answer = resp.answer or "(no response)"
    return (
        f"Survey response from {player_name} (survey {resp.survey_id}): "
        f"Q: {resp.question} A: {answer}."
    )


# ── Point ID generation ───────────────────────────────────────────────────────

def _point_id(team_id: int, doc_type: str, entity_id: int, chunk_idx: int = 0) -> str:
    raw = f"{team_id}:{doc_type}:{entity_id}:{chunk_idx}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Core ingestion function ───────────────────────────────────────────────────

async def ingest_team_data(team_id: int, db: AsyncSession) -> dict:
    """Read all team data from Postgres and upsert into Qdrant.

    Returns a summary dict: {doc_type: count_upserted}.
    """
    from qdrant_client.models import PointStruct  # lazy

    client = _get_qdrant()
    splitter = _get_splitter()
    await ensure_collection(client)

    summary: dict[str, int] = {}
    points: list = []

    # ── Players ───────────────────────────────────────────────────────────────
    result = await db.execute(select(Player).where(Player.team_id == team_id))
    players = result.scalars().all()
    player_map: dict[int, str] = {}

    for player in players:
        player_map[player.id] = player.name
        text = _fmt_player(player)
        chunks = splitter.split_text(text)
        for idx, chunk in enumerate(chunks):
            points.append(PointStruct(
                id=_point_id(team_id, "player", player.id, idx),
                vector=(await embed_texts([chunk]))[0],
                payload={
                    "team_id": team_id,
                    "doc_type": "player",
                    "entity_id": player.id,
                    "chunk_idx": idx,
                    "text": chunk,
                    "last_updated": datetime.now(UTC).isoformat(),
                },
            ))
    summary["player"] = len(players)

    # ── Games ─────────────────────────────────────────────────────────────────
    result = await db.execute(select(Game).where(Game.team_id == team_id))
    games = result.scalars().all()
    for game in games:
        text = _fmt_game(game)
        chunks = splitter.split_text(text)
        for idx, chunk in enumerate(chunks):
            points.append(PointStruct(
                id=_point_id(team_id, "game", game.id, idx),
                vector=(await embed_texts([chunk]))[0],
                payload={
                    "team_id": team_id,
                    "doc_type": "game",
                    "entity_id": game.id,
                    "chunk_idx": idx,
                    "text": chunk,
                    "last_updated": game.created_at.isoformat(),
                },
            ))
    summary["game"] = len(games)

    # ── Player preferences ────────────────────────────────────────────────────
    if player_map:
        player_ids = list(player_map.keys())
        result = await db.execute(
            select(PlayerPreference).where(PlayerPreference.player_id.in_(player_ids))
        )
        prefs = result.scalars().all()
        for pref in prefs:
            pname = player_map.get(pref.player_id, f"player_{pref.player_id}")
            text = _fmt_preference(pref, pname)
            chunks = splitter.split_text(text)
            for idx, chunk in enumerate(chunks):
                points.append(PointStruct(
                    id=_point_id(team_id, "preference", pref.id, idx),
                    vector=(await embed_texts([chunk]))[0],
                    payload={
                        "team_id": team_id,
                        "doc_type": "preference",
                        "entity_id": pref.id,
                        "chunk_idx": idx,
                        "text": chunk,
                        "last_updated": pref.updated_at.isoformat(),
                    },
                ))
        summary["preference"] = len(prefs)

    # ── Survey responses ──────────────────────────────────────────────────────
    if player_map:
        result = await db.execute(
            select(SurveyResponse).where(SurveyResponse.player_id.in_(player_ids))
        )
        survey_resps = result.scalars().all()
        for resp in survey_resps:
            pname = player_map.get(resp.player_id, f"player_{resp.player_id}")
            text = _fmt_survey(resp, pname)
            points.append(PointStruct(
                id=_point_id(team_id, "survey", resp.id),
                vector=(await embed_texts([text]))[0],
                payload={
                    "team_id": team_id,
                    "doc_type": "survey",
                    "entity_id": resp.id,
                    "chunk_idx": 0,
                    "text": text,
                    "last_updated": resp.created_at.isoformat(),
                },
            ))
        summary["survey"] = len(survey_resps)

    # ── Batch upsert to Qdrant ────────────────────────────────────────────────
    if points:
        BATCH = 100
        for start in range(0, len(points), BATCH):
            await client.upsert(
                collection_name=COLLECTION_NAME,
                points=points[start : start + BATCH],
            )

    await client.close()
    log.info("ingestion.done team_id=%d summary=%s", team_id, summary)
    return summary
