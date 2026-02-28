from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_captain
from app.db import get_db
from app.models.player import Player
from app.models.team import Team
from app.models.user import User
from app.schemas import PlayerReadCaptain, TeamCreate, TeamRead, TeamUpdate

router = APIRouter(prefix="/api/teams", tags=["teams"])


async def _get_own_team(team_id: int, db: AsyncSession, captain: User) -> Team:
    """Fetch a team by id, verifying it belongs to the requesting captain."""
    result = await db.execute(
        select(Team).where(Team.id == team_id, Team.captain_id == captain.id)
    )
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


@router.get("", response_model=list[TeamRead])
async def list_teams(
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Team).where(Team.captain_id == captain.id))
    return result.scalars().all()


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team(
    body: TeamCreate,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    team = Team(name=body.name, captain_id=captain.id)
    db.add(team)
    await db.commit()
    await db.refresh(team)
    return team


@router.get("/{team_id}", response_model=TeamRead)
async def get_team(
    team_id: int,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await _get_own_team(team_id, db, captain)


@router.patch("/{team_id}", response_model=TeamRead)
async def update_team(
    team_id: int,
    body: TeamUpdate,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    team = await _get_own_team(team_id, db, captain)
    if body.name is not None:
        team.name = body.name
    await db.commit()
    await db.refresh(team)
    return team


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: int,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    team = await _get_own_team(team_id, db, captain)
    await db.delete(team)
    await db.commit()


@router.get("/{team_id}/players", response_model=list[PlayerReadCaptain])
async def team_roster(
    team_id: int,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_own_team(team_id, db, captain)
    result = await db.execute(select(Player).where(Player.team_id == team_id))
    return result.scalars().all()
