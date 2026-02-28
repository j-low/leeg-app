from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_captain
from app.db import get_db
from app.models.season import Season
from app.models.team_season import TeamSeason
from app.models.user import User
from app.schemas import SeasonCreate, SeasonRead, SeasonUpdate

router = APIRouter(prefix="/api/seasons", tags=["seasons"])


async def _get_season(season_id: int, db: AsyncSession) -> Season:
    result = await db.execute(select(Season).where(Season.id == season_id))
    season = result.scalar_one_or_none()
    if not season:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    return season


@router.get("", response_model=list[SeasonRead])
async def list_seasons(
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Season).order_by(Season.start_date.desc()))
    return result.scalars().all()


@router.post("", response_model=SeasonRead, status_code=status.HTTP_201_CREATED)
async def create_season(
    body: SeasonCreate,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    season = Season(**body.model_dump())
    db.add(season)
    await db.commit()
    await db.refresh(season)
    return season


@router.get("/{season_id}", response_model=SeasonRead)
async def get_season(
    season_id: int,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await _get_season(season_id, db)


@router.patch("/{season_id}", response_model=SeasonRead)
async def update_season(
    season_id: int,
    body: SeasonUpdate,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    season = await _get_season(season_id, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(season, field, value)
    await db.commit()
    await db.refresh(season)
    return season


@router.post("/{season_id}/teams/{team_id}", status_code=status.HTTP_201_CREATED)
async def link_team_to_season(
    season_id: int,
    team_id: int,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_season(season_id, db)
    existing = await db.execute(
        select(TeamSeason).where(
            TeamSeason.season_id == season_id,
            TeamSeason.team_id == team_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Team already linked to this season",
        )
    db.add(TeamSeason(season_id=season_id, team_id=team_id))
    await db.commit()
    return {"season_id": season_id, "team_id": team_id}
