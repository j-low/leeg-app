from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_captain
from app.db import get_db
from app.models.lineup import Lineup
from app.models.user import User
from app.schemas import LineupCreate, LineupRead

router = APIRouter(prefix="/api/lineups", tags=["lineups"])


@router.get("", response_model=list[LineupRead])
async def list_lineups(
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
    game_id: int | None = Query(None),
    team_id: int | None = Query(None),
):
    stmt = select(Lineup)
    if game_id is not None:
        stmt = stmt.where(Lineup.game_id == game_id)
    if team_id is not None:
        stmt = stmt.where(Lineup.team_id == team_id)
    stmt = stmt.order_by(Lineup.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{lineup_id}", response_model=LineupRead)
async def get_lineup(
    lineup_id: int,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Lineup).where(Lineup.id == lineup_id))
    lineup = result.scalar_one_or_none()
    if not lineup:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lineup not found")
    return lineup


@router.post("/suggest", response_model=LineupRead, status_code=status.HTTP_201_CREATED)
async def suggest_lineup(
    body: LineupCreate,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # TODO (Phase 7): invoke AI pipeline to generate lineup suggestion.
    # For now, persist the provided lineup as-is.
    lineup = Lineup(**body.model_dump())
    db.add(lineup)
    await db.commit()
    await db.refresh(lineup)
    return lineup
