from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_captain
from app.db import get_db
from app.models.attendance import Attendance, AttendanceStatus
from app.models.game import Game
from app.models.user import User
from app.schemas import AttendanceRead, AttendanceSummary, AttendanceUpsert, GameCreate, GameRead, GameUpdate

router = APIRouter(prefix="/api/games", tags=["games"])


async def _get_game(game_id: int, db: AsyncSession) -> Game:
    result = await db.execute(select(Game).where(Game.id == game_id))
    game = result.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Game not found")
    return game


@router.get("", response_model=list[GameRead])
async def list_games(
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
    team_id: int | None = Query(None),
    season_id: int | None = Query(None),
):
    stmt = select(Game)
    if team_id is not None:
        stmt = stmt.where(Game.team_id == team_id)
    if season_id is not None:
        stmt = stmt.where(Game.season_id == season_id)
    stmt = stmt.order_by(Game.game_date)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=GameRead, status_code=status.HTTP_201_CREATED)
async def create_game(
    body: GameCreate,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    game = Game(**body.model_dump())
    db.add(game)
    await db.commit()
    await db.refresh(game)
    return game


@router.get("/{game_id}", response_model=GameRead)
async def get_game(
    game_id: int,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await _get_game(game_id, db)


@router.patch("/{game_id}", response_model=GameRead)
async def update_game(
    game_id: int,
    body: GameUpdate,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    game = await _get_game(game_id, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(game, field, value)
    await db.commit()
    await db.refresh(game)
    return game


@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_game(
    game_id: int,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    game = await _get_game(game_id, db)
    await db.delete(game)
    await db.commit()


@router.get("/{game_id}/attendance", response_model=AttendanceSummary)
async def get_attendance_summary(
    game_id: int,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_game(game_id, db)
    result = await db.execute(select(Attendance).where(Attendance.game_id == game_id))
    records = result.scalars().all()
    summary = AttendanceSummary(game_id=game_id, total_players=len(records))
    for rec in records:
        if rec.status == AttendanceStatus.yes:
            summary.yes += 1
        elif rec.status == AttendanceStatus.no:
            summary.no += 1
        else:
            summary.maybe += 1
    return summary


@router.put("/{game_id}/attendance", response_model=AttendanceRead)
async def upsert_attendance(
    game_id: int,
    body: AttendanceUpsert,
    captain: Annotated[User, Depends(require_captain)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await _get_game(game_id, db)
    result = await db.execute(
        select(Attendance).where(
            Attendance.game_id == game_id,
            Attendance.player_id == body.player_id,
        )
    )
    attendance = result.scalar_one_or_none()
    if attendance:
        attendance.status = body.status
    else:
        attendance = Attendance(game_id=game_id, player_id=body.player_id, status=body.status)
        db.add(attendance)
    await db.commit()
    await db.refresh(attendance)
    return attendance
