"""
Stage 3: Tool definitions for Claude tool use.

Each tool is defined in two parts:
  - A schema dict in Claude's tool use format (name, description, input_schema)
    that the LLM reasons about when deciding what to call.
  - An async Python implementation that executes the actual side effect.

The TOOL_SCHEMAS list is passed directly to the Anthropic API as `tools=`.
TOOL_REGISTRY maps tool names to their implementations for dispatch in agent.py.

All DB-writing tools (update_attendance, update_player_prefs) use upsert
semantics so they are idempotent across agent loop retries.
"""
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import Attendance, AttendanceStatus
from app.models.game import Game
from app.models.player import Player
from app.models.player_preference import PlayerPreference

log = logging.getLogger(__name__)


# ── Tool schemas (passed to Anthropic API as tools=[...]) ─────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "update_attendance",
        "description": (
            "Record a player's attendance status for a specific game. "
            "Status must be one of: 'yes', 'no', 'maybe'. "
            "Uses upsert so calling twice is safe."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "game_id":   {"type": "integer", "description": "ID of the game"},
                "player_id": {"type": "integer", "description": "ID of the player"},
                "status":    {
                    "type": "string",
                    "enum": ["yes", "no", "maybe"],
                    "description": "Attendance status",
                },
            },
            "required": ["game_id", "player_id", "status"],
        },
    },
    {
        "name": "get_attendance",
        "description": "Return all attendance records for a game, with player names and statuses.",
        "input_schema": {
            "type": "object",
            "properties": {
                "game_id": {"type": "integer", "description": "ID of the game"},
            },
            "required": ["game_id"],
        },
    },
    {
        "name": "get_roster",
        "description": (
            "Return the full player roster for a team including names, "
            "position preferences, skill notes, and sub availability."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team_id": {"type": "integer", "description": "ID of the team"},
            },
            "required": ["team_id"],
        },
    },
    {
        "name": "get_player_prefs",
        "description": (
            "Return a player's stored preferences: preferred positions, "
            "ice time constraints, and style notes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "player_id": {"type": "integer", "description": "ID of the player"},
            },
            "required": ["player_id"],
        },
    },
    {
        "name": "update_player_prefs",
        "description": (
            "Update a player's stored preferences. Only provide fields that "
            "should change; omitted fields are left unchanged."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "player_id": {"type": "integer", "description": "ID of the player"},
                "position_prefs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Preferred positions e.g. ['wing', 'center']",
                },
                "ice_time_constraints": {
                    "type": "string",
                    "description": "Free-text ice time constraints",
                },
                "style_notes": {
                    "type": "string",
                    "description": "Free-text playing style notes",
                },
            },
            "required": ["player_id"],
        },
    },
    {
        "name": "search_schedule",
        "description": (
            "Search for upcoming or recent games matching a natural-language description "
            "(e.g. 'next Tuesday', 'this weekend', 'March 15'). "
            "Returns game IDs, dates, times, and locations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query":   {"type": "string", "description": "Natural language date/game description"},
                "team_id": {"type": "integer", "description": "Team to search within"},
            },
            "required": ["query", "team_id"],
        },
    },
    {
        "name": "send_sms",
        "description": "Send an SMS message to a single player.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to_phone": {"type": "string", "description": "E.164 phone number e.g. +16135550101"},
                "message":  {"type": "string", "description": "Message text (≤ 160 chars for single SMS)"},
            },
            "required": ["to_phone", "message"],
        },
    },
    {
        "name": "send_group_sms",
        "description": (
            "Send an SMS message to multiple players simultaneously. "
            "Use for broadcasts, sub requests, and reminders."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to_phones": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of E.164 phone numbers",
                },
                "message": {"type": "string", "description": "Message text"},
            },
            "required": ["to_phones", "message"],
        },
    },
]


# ── Tool implementations ───────────────────────────────────────────────────────

async def _update_attendance(game_id: int, player_id: int, status: str, db: AsyncSession) -> dict:
    stmt = (
        pg_insert(Attendance)
        .values(game_id=game_id, player_id=player_id, status=AttendanceStatus(status))
        .on_conflict_do_update(
            index_elements=["game_id", "player_id"],
            set_={"status": AttendanceStatus(status)},
        )
    )
    await db.execute(stmt)
    await db.commit()
    log.info("tool.update_attendance game_id=%d player_id=%d status=%s", game_id, player_id, status)
    return {"ok": True, "game_id": game_id, "player_id": player_id, "status": status}


async def _get_attendance(game_id: int, db: AsyncSession) -> dict:
    result = await db.execute(
        select(Attendance, Player)
        .join(Player, Attendance.player_id == Player.id)
        .where(Attendance.game_id == game_id)
    )
    rows = result.all()
    records = [
        {"player_id": att.id, "player_name": p.name, "status": att.status.value}
        for att, p in rows
    ]
    return {"game_id": game_id, "attendance": records}


async def _get_roster(team_id: int, db: AsyncSession) -> dict:
    result = await db.execute(select(Player).where(Player.team_id == team_id))
    players = result.scalars().all()
    return {
        "team_id": team_id,
        "players": [
            {
                "id": p.id,
                "name": p.name,
                "position_prefs": p.position_prefs or [],
                "skill_notes": p.skill_notes or "",
                "sub_flag": p.sub_flag,
            }
            for p in players
        ],
    }


async def _get_player_prefs(player_id: int, db: AsyncSession) -> dict:
    result = await db.execute(
        select(PlayerPreference).where(PlayerPreference.player_id == player_id)
    )
    pref = result.scalars().first()
    if pref is None:
        return {"player_id": player_id, "prefs": None}
    return {
        "player_id": player_id,
        "prefs": {
            "position_prefs": pref.position_prefs or [],
            "ice_time_constraints": pref.ice_time_constraints or "",
            "style_notes": pref.style_notes or "",
        },
    }


async def _update_player_prefs(
    player_id: int,
    db: AsyncSession,
    position_prefs: list[str] | None = None,
    ice_time_constraints: str | None = None,
    style_notes: str | None = None,
) -> dict:
    result = await db.execute(
        select(PlayerPreference).where(PlayerPreference.player_id == player_id)
    )
    pref = result.scalars().first()
    if pref is None:
        pref = PlayerPreference(player_id=player_id)
        db.add(pref)
    if position_prefs is not None:
        pref.position_prefs = position_prefs
    if ice_time_constraints is not None:
        pref.ice_time_constraints = ice_time_constraints
    if style_notes is not None:
        pref.style_notes = style_notes
    await db.commit()
    log.info("tool.update_player_prefs player_id=%d", player_id)
    return {"ok": True, "player_id": player_id}


async def _search_schedule(query: str, team_id: int, db: AsyncSession) -> dict:
    # Simple implementation: return next 5 upcoming games for this team.
    # A more sophisticated version would parse dates from `query`.
    from datetime import UTC, datetime
    result = await db.execute(
        select(Game)
        .where(Game.team_id == team_id)
        .where(Game.game_date >= datetime.now(UTC).date())
        .order_by(Game.game_date)
        .limit(5)
    )
    games = result.scalars().all()
    return {
        "query": query,
        "games": [
            {
                "id": g.id,
                "date": str(g.game_date),
                "time": str(g.game_time) if g.game_time else None,
                "location": g.location,
                "notes": g.notes,
            }
            for g in games
        ],
    }


async def _send_sms(to_phone: str, message: str) -> dict:
    from app.config import settings
    from app.sms import send_sms as twilio_send

    if not settings.twilio_account_sid:
        log.warning("tool.send_sms skipped — Twilio not configured")
        return {"ok": False, "reason": "Twilio not configured", "to": to_phone}
    await twilio_send(to_phone, message)
    log.info("tool.send_sms to=%s", to_phone)
    return {"ok": True, "to": to_phone, "message": message}


async def _send_group_sms(to_phones: list[str], message: str) -> dict:
    from app.config import settings
    from app.sms import send_sms as twilio_send

    if not settings.twilio_account_sid:
        log.warning("tool.send_group_sms skipped — Twilio not configured")
        return {"ok": False, "reason": "Twilio not configured", "count": 0}
    for phone in to_phones:
        await twilio_send(phone, message)
    log.info("tool.send_group_sms count=%d", len(to_phones))
    return {"ok": True, "count": len(to_phones)}


# ── Dispatcher ────────────────────────────────────────────────────────────────

async def dispatch_tool(name: str, inputs: dict[str, Any], db: AsyncSession) -> Any:
    """Call the named tool with the given inputs and return its result.

    Args:
        name:   Tool name as returned in a Claude tool_use block.
        inputs: The `input` dict from the tool_use block.
        db:     Active AsyncSession (injected by the caller).

    Returns:
        A JSON-serialisable dict result ready to feed back as a tool_result.

    Raises:
        ValueError: If the tool name is unknown.
    """
    match name:
        case "update_attendance":
            return await _update_attendance(
                game_id=inputs["game_id"],
                player_id=inputs["player_id"],
                status=inputs["status"],
                db=db,
            )
        case "get_attendance":
            return await _get_attendance(game_id=inputs["game_id"], db=db)
        case "get_roster":
            return await _get_roster(team_id=inputs["team_id"], db=db)
        case "get_player_prefs":
            return await _get_player_prefs(player_id=inputs["player_id"], db=db)
        case "update_player_prefs":
            return await _update_player_prefs(
                player_id=inputs["player_id"],
                db=db,
                position_prefs=inputs.get("position_prefs"),
                ice_time_constraints=inputs.get("ice_time_constraints"),
                style_notes=inputs.get("style_notes"),
            )
        case "search_schedule":
            return await _search_schedule(
                query=inputs["query"],
                team_id=inputs["team_id"],
                db=db,
            )
        case "send_sms":
            return await _send_sms(to_phone=inputs["to_phone"], message=inputs["message"])
        case "send_group_sms":
            return await _send_group_sms(
                to_phones=inputs["to_phones"],
                message=inputs["message"],
            )
        case _:
            raise ValueError(f"Unknown tool: {name!r}")
