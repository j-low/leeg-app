"""
Seed script: inserts realistic sample data for local development and integration testing.

Usage:
    source venv/bin/activate
    python scripts/seed_data.py

Idempotent: safe to run multiple times -- skips records that already exist
(detected by email for users, phone for players, and name matches for others).
"""

import asyncio
import sys
from datetime import date, time
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session
from app.models import (
    Attendance, AttendanceStatus, Game, Lineup, MessageLog, MessageType,
    Player, PlayerPreference, Season, SeasonStatus, SurveyResponse,
    SurveyScope, Team, TeamSeason, User,
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Seed data definitions
# ---------------------------------------------------------------------------

CAPTAIN_EMAIL = "captain@leeg.dev"
CAPTAIN_PASSWORD = "leegdev2024"
TEAM_NAME = "The Mighty Pucks"

PLAYERS = [
    {"name": "Alice Tremblay",  "phone": "+16135550101", "position_prefs": ["center"],           "skill_notes": "Strong two-way forward, good on draws",       "sub_flag": False},
    {"name": "Bob Nguyen",      "phone": "+16135550102", "position_prefs": ["wing", "center"],   "skill_notes": "Fast winger, prefers right side",             "sub_flag": False},
    {"name": "Carol MacLeod",   "phone": "+16135550103", "position_prefs": ["defense"],          "skill_notes": "Stay-at-home D, solid positioning",           "sub_flag": False},
    {"name": "Dan Okafor",      "phone": "+16135550104", "position_prefs": ["defense"],          "skill_notes": "Rushing D, good shot from the point",         "sub_flag": False},
    {"name": "Eva Kowalski",    "phone": "+16135550105", "position_prefs": ["wing"],             "skill_notes": "Left winger, physical presence",              "sub_flag": False},
    {"name": "Frank Bouchard",  "phone": "+16135550106", "position_prefs": ["center", "wing"],   "skill_notes": "Versatile forward, strong defensive zone",    "sub_flag": False},
    {"name": "Grace Chen",      "phone": "+16135550107", "position_prefs": ["goalie"],           "skill_notes": "Primary goalie, butterfly style",             "sub_flag": False},
    {"name": "Henry Patel",     "phone": "+16135550108", "position_prefs": ["defense", "wing"],  "skill_notes": "Utility player, can play D or wing in a pinch","sub_flag": False},
    {"name": "Isla Morrison",   "phone": "+16135550109", "position_prefs": ["wing"],             "skill_notes": "Speedy right winger, good hands",             "sub_flag": False},
    {"name": "Jake Leblanc",    "phone": "+16135550110", "position_prefs": ["center"],           "skill_notes": "Defensive center, strong penalty killer",     "sub_flag": False},
    {"name": "Karen Dubois",    "phone": "+16135550111", "position_prefs": ["defense"],          "skill_notes": "Steady D, good first pass",                   "sub_flag": False},
    {"name": "Leo Santos",      "phone": "+16135550112", "position_prefs": ["wing", "center"],   "skill_notes": "Power forward, likes to drive the net",       "sub_flag": False},
    {"name": "Mia Andersen",    "phone": "+16135550113", "position_prefs": ["goalie"],           "skill_notes": "Backup goalie, quick glove hand",             "sub_flag": True },
    {"name": "Nick Thompson",   "phone": "+16135550114", "position_prefs": ["wing"],             "skill_notes": "Available as sub most Tuesdays",              "sub_flag": True },
    {"name": "Olivia Park",     "phone": "+16135550115", "position_prefs": ["defense", "wing"],  "skill_notes": "Regular sub, skating has improved a lot",     "sub_flag": True },
]

PLAYER_PREFS = {
    "+16135550101": {"ice_time_constraints": "Available all nights", "style_notes": "Prefers structured systems play"},
    "+16135550102": {"ice_time_constraints": "Not available Thursdays", "style_notes": "Likes open ice, fast transitions"},
    "+16135550107": {"ice_time_constraints": "Can only do one game per week", "style_notes": "Needs 10 min warmup before first shot"},
}

PAST_LINEUPS = [
    {
        "lines": [[1, 2, 5], [6, 10, 12], [3, 4], [8, 11], [7]],
        "criteria": "Balance lines by position and skill level",
        "explanation": "Line 1: Alice-Bob-Eva (skilled forwards). Line 2: Frank-Jake-Leo (defensive). D pairs: Carol-Dan and Henry-Karen. Grace in net.",
    }
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def get_or_create(session: AsyncSession, model, lookup_kwargs: dict, create_kwargs: dict):
    """Fetch existing record or create a new one. Returns (obj, created: bool)."""
    stmt = select(model).filter_by(**lookup_kwargs)
    result = await session.execute(stmt)
    obj = result.scalar_one_or_none()
    if obj:
        return obj, False
    obj = model(**lookup_kwargs, **create_kwargs)
    session.add(obj)
    await session.flush()
    return obj, True


def log(msg: str) -> None:
    print(f"  {msg}")


# ---------------------------------------------------------------------------
# Main seed function
# ---------------------------------------------------------------------------

async def seed() -> None:
    async with async_session() as session:
        async with session.begin():
            print("\n── Users ──────────────────────────────────────")
            captain, created = await get_or_create(
                session, User,
                lookup_kwargs={"email": CAPTAIN_EMAIL},
                create_kwargs={
                    "hashed_password": pwd_context.hash(CAPTAIN_PASSWORD),
                    "phone": "+16135550100",
                    "is_captain": True,
                    "is_active": True,
                },
            )
            log(f"Captain: {captain.email} ({'created' if created else 'exists'})")

            print("\n── Team ──────────────────────────────────────")
            team, created = await get_or_create(
                session, Team,
                lookup_kwargs={"name": TEAM_NAME, "captain_id": captain.id},
                create_kwargs={},
            )
            log(f"Team: {team.name} ({'created' if created else 'exists'})")

            print("\n── Players ──────────────────────────────────")
            player_objs: list[Player] = []
            for p in PLAYERS:
                player, created = await get_or_create(
                    session, Player,
                    lookup_kwargs={"phone": p["phone"]},
                    create_kwargs={
                        "name": p["name"],
                        "team_id": team.id,
                        "position_prefs": p["position_prefs"],
                        "skill_notes": p["skill_notes"],
                        "sub_flag": p["sub_flag"],
                    },
                )
                player_objs.append(player)
                log(f"  {'[sub] ' if player.sub_flag else '      '}{player.name} ({player.phone}) ({'created' if created else 'exists'})")

            print("\n── Player Preferences ───────────────────────")
            for player in player_objs:
                if player.phone in PLAYER_PREFS:
                    pref_data = PLAYER_PREFS[player.phone]
                    pref, created = await get_or_create(
                        session, PlayerPreference,
                        lookup_kwargs={"player_id": player.id},
                        create_kwargs={
                            "position_prefs": player.position_prefs,
                            **pref_data,
                        },
                    )
                    log(f"{player.name}: ({'created' if created else 'exists'})")

            print("\n── Season ────────────────────────────────────")
            season, created = await get_or_create(
                session, Season,
                lookup_kwargs={"name": "Winter 2025"},
                create_kwargs={
                    "start_date": date(2025, 1, 7),
                    "end_date": date(2025, 3, 25),
                    "status": SeasonStatus.open,
                },
            )
            log(f"Season: {season.name} ({season.status.value}) ({'created' if created else 'exists'})")

            # Link team to season
            _, created = await get_or_create(
                session, TeamSeason,
                lookup_kwargs={"team_id": team.id, "season_id": season.id},
                create_kwargs={},
            )
            log(f"TeamSeason link: ({'created' if created else 'exists'})")

            print("\n── Games ─────────────────────────────────────")
            games_data = [
                {"game_date": date(2025, 2, 4),  "game_time": time(20, 0), "location": "Bell Sensplex - Rink 2", "notes": "Regular season game"},
                {"game_date": date(2025, 2, 11), "game_time": time(21, 0), "location": "Bell Sensplex - Rink 1", "notes": "Regular season game"},
                {"game_date": date(2025, 2, 18), "game_time": time(20, 0), "location": "Richcraft Sensplex",     "notes": "Away game - carpool organized"},
                {"game_date": date(2025, 2, 25), "game_time": time(21, 30),"location": "Bell Sensplex - Rink 2", "notes": "Late ice"},
                {"game_date": date(2025, 3, 4),  "game_time": time(20, 0), "location": "Bell Sensplex - Rink 1", "notes": None},
            ]
            game_objs: list[Game] = []
            for g in games_data:
                game, created = await get_or_create(
                    session, Game,
                    lookup_kwargs={"game_date": g["game_date"], "season_id": season.id, "team_id": team.id},
                    create_kwargs={
                        "game_time": g["game_time"],
                        "location": g["location"],
                        "notes": g["notes"],
                    },
                )
                game_objs.append(game)
                log(f"Game {game.game_date} @ {game.location} ({'created' if created else 'exists'})")

            print("\n── Attendance (Game 1 - already played) ─────")
            first_game = game_objs[0]
            attendance_data = [
                # Most players confirmed yes
                *[(p, AttendanceStatus.yes) for p in player_objs[:10]],
                # A couple no/maybe
                (player_objs[10], AttendanceStatus.no),
                (player_objs[11], AttendanceStatus.maybe),
            ]
            for player, status in attendance_data:
                att, created = await get_or_create(
                    session, Attendance,
                    lookup_kwargs={"game_id": first_game.id, "player_id": player.id},
                    create_kwargs={"status": status},
                )
                if created:
                    log(f"  {player.name}: {status.value}")

            print("\n── Past Lineup (Game 1) ─────────────────────")
            lineup_data = PAST_LINEUPS[0]
            # Convert positional line indices to actual player IDs
            resolved_lines = [
                [player_objs[idx - 1].id for idx in line]
                for line in lineup_data["lines"]
            ]
            _, created = await get_or_create(
                session, Lineup,
                lookup_kwargs={"game_id": first_game.id, "team_id": team.id},
                create_kwargs={
                    "proposed_lines": resolved_lines,
                    "criteria": lineup_data["criteria"],
                    "explanation": lineup_data["explanation"],
                },
            )
            log(f"Lineup for game {first_game.game_date}: ({'created' if created else 'exists'})")

            print("\n── Message Log (sample) ─────────────────────")
            # One sample broadcast so message_logs table isn't empty for RAG
            log_entry, created = await get_or_create(
                session, MessageLog,
                lookup_kwargs={"from_phone": captain.phone, "msg_type": MessageType.reminder},
                create_kwargs={
                    "to_phones": [p.phone for p in player_objs if not p.sub_flag],
                    "content": "Hey team! Game Tuesday Feb 4 at 8pm - Sensplex Rink 2. Please confirm attendance.",
                },
            )
            log(f"Message log: ({'created' if created else 'exists'})")

        print("\n✓ Seed complete.\n")
        print(f"  Captain login: {CAPTAIN_EMAIL} / {CAPTAIN_PASSWORD}")
        print(f"  Team: '{TEAM_NAME}' with {len(PLAYERS)} players")
        print(f"  Season: Winter 2025 with {len(games_data)} games\n")


if __name__ == "__main__":
    asyncio.run(seed())
