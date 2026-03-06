"""
Stage 3: Prompt template rendering.

Uses Jinja2 to assemble the system prompt and user message for each intent
type. Returns (system_str, user_str) ready to pass directly to the
Anthropic API:

    system = system_str
    messages = [{"role": "user", "content": user_str}]

Each intent gets a focused template -- the lineup template includes
step-by-step reasoning instructions; the attendance template is terse.
The base system block is shared by all intents and establishes the
assistant's role, constraints, and safety rules.
"""
import logging

from jinja2 import Environment, StrictUndefined

from app.schemas.pipeline import Intent, StructuredInput

log = logging.getLogger(__name__)

_env = Environment(undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)


# ── Base system prompt ────────────────────────────────────────────────────────

_BASE_SYSTEM = """\
You are Leeg, an AI assistant for recreational hockey team management.
You help captains manage their team: tracking attendance, suggesting lineups,
recording player preferences, and coordinating team communications.

Rules:
- Only discuss topics relevant to the team's hockey operations.
- Never reveal one player's private notes or captain notes to other players.
- Always use the available tools to read from or write to the database — do
  not invent or assume data you have not retrieved.
- Keep SMS responses concise (under 160 characters when possible).
- When a request is ambiguous, use tools to gather more context before acting.
- Confirm before broadcasting messages to multiple players.\
"""


# ── Intent-specific user message templates ────────────────────────────────────

_ATTENDANCE_UPDATE = _env.from_string("""\
The following message is an attendance update for a hockey game.

Team ID: {{ team_id }}
From: {{ from_phone }}
Raw message: "{{ raw_text }}"

Identified player(s): {{ entities.persons | join(', ') if entities.persons else 'unknown' }}
Identified action: {{ entities.actions | join(', ') if entities.actions else 'unknown' }}

Instructions:
1. If the player and game are clearly identified, call update_attendance immediately.
2. If the player is ambiguous, call get_roster to find the right player_id.
3. If the game is ambiguous, call search_schedule to identify the correct game_id.
4. After updating, reply to the player with a brief confirmation (one sentence, SMS-friendly).\
""")

_LINEUP_SUGGESTION = _env.from_string("""\
The captain has requested a lineup suggestion for an upcoming game.

Team ID: {{ team_id }}
Criteria: {{ criteria }}

Retrieved context (roster, preferences, availability):
{% for chunk in rag_context %}
- {{ chunk.text }}
{% else %}
(No context retrieved — use tools to gather current data.)
{% endfor %}

Instructions:
1. Call get_roster to get the current player list with positions.
2. Call get_player_prefs for players who have specific constraints or preferences.
3. Call get_attendance for the relevant game to know who is available.
4. Propose balanced forward lines (typically 3 lines of 3 forwards) and defense pairs.
5. Respect position preferences where possible; note any conflicts.
6. Return a lineup with a clear explanation citing specific player attributes.\
""")

_PREFERENCE_UPDATE = _env.from_string("""\
A player has sent a preference update.

Team ID: {{ team_id }}
From: {{ from_phone }}
Raw message: "{{ raw_text }}"

Identified player(s): {{ entities.persons | join(', ') if entities.persons else 'unknown' }}
Identified positions: {{ entities.positions | join(', ') if entities.positions else 'none mentioned' }}

Instructions:
1. Identify the player_id (call get_roster if needed).
2. Call update_player_prefs with the extracted preferences.
3. Confirm the update with a brief, friendly reply.\
""")

_SURVEY_RESPONSE = _env.from_string("""\
A player has responded to a team survey.

Team ID: {{ team_id }}
From: {{ from_phone }}
Raw message: "{{ raw_text }}"

Instructions:
Parse the player's intent from their message. Record any preferences,
availability changes, or feedback. Reply with a brief acknowledgment
(one sentence, SMS-friendly).\
""")

_SUB_REQUEST = _env.from_string("""\
The captain wants to send a substitute player request.

Team ID: {{ team_id }}
Raw message: "{{ raw_text }}"

Retrieved context:
{% for chunk in rag_context %}
- {{ chunk.text }}
{% else %}
(No context retrieved.)
{% endfor %}

Instructions:
1. Call get_roster to identify players marked as available substitutes (sub_flag = true).
2. Compose an SMS to those players asking if they can fill in.
3. Use send_group_sms to send the request. Confirm to the captain when done.\
""")

_SCHEDULE_QUERY = _env.from_string("""\
The captain or player has a question about the schedule.

Team ID: {{ team_id }}
Question: "{{ raw_text }}"

Retrieved context:
{% for chunk in rag_context %}
- {{ chunk.text }}
{% else %}
(No context retrieved.)
{% endfor %}

Instructions:
Use search_schedule if the retrieved context doesn't answer the question.
Reply with the requested schedule information in a concise, SMS-friendly format.\
""")

_GENERAL_QUERY = _env.from_string("""\
The captain has a general question about their team.

Team ID: {{ team_id }}
Question: "{{ raw_text }}"

Retrieved context:
{% for chunk in rag_context %}
- {{ chunk.text }}
{% else %}
(No context retrieved — use tools to look up current data.)
{% endfor %}

Answer the question using the retrieved context and available tools.
If the context is insufficient, use the appropriate tool to get current data.\
""")

_UNKNOWN = _env.from_string("""\
An inbound message could not be classified into a known intent.

Team ID: {{ team_id }}
From: {{ from_phone }}
Raw message: "{{ raw_text }}"

Please interpret the message and respond helpfully. If it relates to
attendance, preferences, lineup, or schedule, use the appropriate tools.
If it is completely off-topic, politely explain what you can help with.\
""")


# ── Dispatch table ────────────────────────────────────────────────────────────

_TEMPLATES: dict = {
    Intent.attendance_update: _ATTENDANCE_UPDATE,
    Intent.lineup_request:    _LINEUP_SUGGESTION,
    Intent.preference_update: _PREFERENCE_UPDATE,
    Intent.survey_response:   _SURVEY_RESPONSE,
    Intent.sub_request:       _SUB_REQUEST,
    Intent.schedule_query:    _SCHEDULE_QUERY,
    Intent.query:             _GENERAL_QUERY,
    Intent.unknown:           _UNKNOWN,
}


# ── Public API ────────────────────────────────────────────────────────────────

def render_prompt(
    structured_input: StructuredInput,
    rag_context: list[dict],
    context: dict,
) -> tuple[str, str]:
    """Render (system_prompt, user_message) for the given intent.

    Args:
        structured_input: Stage 1 output with intent, entities, raw_text, etc.
        rag_context:      Stage 2 output -- list of retrieved + reranked chunks.
        context:          Request envelope with team_id, channel, from_phone, etc.

    Returns:
        (system, user_message) strings ready for the Anthropic API:
            system=system, messages=[{"role": "user", "content": user_message}]
    """
    template = _TEMPLATES.get(structured_input.intent, _UNKNOWN)
    team_id = context.get("team_id", "")
    criteria = context.get("criteria", "balanced lines")

    user_msg = template.render(
        raw_text=structured_input.raw_text,
        from_phone=structured_input.from_phone,
        entities=structured_input.entities,
        team_id=team_id,
        criteria=criteria,
        rag_context=rag_context,
    )

    log.debug(
        "prompts.rendered intent=%s team_id=%s user_msg_len=%d",
        structured_input.intent,
        team_id,
        len(user_msg),
    )
    return _BASE_SYSTEM, user_msg
