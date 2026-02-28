from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_captain
from app.db import get_db
from app.models.player import Player
from app.models.user import User
from app.schemas import PlayerCreate, PlayerReadCaptain, PlayerUpdate

router = APIRouter(prefix="/api/players", tags=["players"])


async def _get_player(player_id: int, db: AsyncSession) -> Player:
    result = await db.execute(select(Player).where(Player.id == player_id))
    player = result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    return player


@router.get("", response_model=list[PlayerReadCaptain])
async def list_players(
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
    team_id: int | None = Query(None),
):
    stmt = select(Player)
    if team_id is not None:
        stmt = stmt.where(Player.team_id == team_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=PlayerReadCaptain, status_code=status.HTTP_201_CREATED)
async def create_player(
    body: PlayerCreate,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    existing = await db.execute(select(Player).where(Player.phone == body.phone))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Phone already registered")
    player = Player(**body.model_dump())
    db.add(player)
    await db.commit()
    await db.refresh(player)
    return player


@router.get("/{player_id}", response_model=PlayerReadCaptain)
async def get_player(
    player_id: int,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await _get_player(player_id, db)


@router.patch("/{player_id}", response_model=PlayerReadCaptain)
async def update_player(
    player_id: int,
    body: PlayerUpdate,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    player = await _get_player(player_id, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(player, field, value)
    await db.commit()
    await db.refresh(player)
    return player


@router.delete("/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_player(
    player_id: int,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    player = await _get_player(player_id, db)
    await db.delete(player)
    await db.commit()
