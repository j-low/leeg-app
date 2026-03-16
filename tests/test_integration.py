"""
Integration tests for Phase 11.

Four test classes — each builds a minimal FastAPI app (no SlowAPI middleware)
against an in-memory SQLite database:

  TestAuthFlow   (8)  — register / login / /me endpoints
  TestCrudFlow   (10) — teams / players / games / attendance
  TestSmsWebhook (8)  — Twilio inbound webhook
  TestChatStream (9)  — SSE dashboard streaming endpoint

All external services are mocked: Redis, Anthropic, Celery, Twilio.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from tests.conftest import build_engine, make_app, make_session_override


# ── TestAuthFlow ──────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestAuthFlow:
    """Auth routes: register → login → /me."""

    async def _make_client(self) -> AsyncClient:
        from app.routes.auth import router
        engine = await build_engine()
        app = make_app(router, db_override=make_session_override(engine))
        return AsyncClient(app=app, base_url="http://test"), engine

    @pytest.mark.asyncio
    async def test_register_returns_201_and_user(self):
        client, engine = await self._make_client()
        async with client as c:
            r = await c.post("/api/auth/register", json={"email": "alice@test.com", "password": "secret123"})
        assert r.status_code == 201
        data = r.json()
        assert data["email"] == "alice@test.com"
        assert data["is_captain"] is True
        assert "hashed_password" not in data
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_register_duplicate_email_returns_409(self):
        client, engine = await self._make_client()
        async with client as c:
            await c.post("/api/auth/register", json={"email": "dup@test.com", "password": "pass1234"})
            r = await c.post("/api/auth/register", json={"email": "dup@test.com", "password": "other123"})
        assert r.status_code == 409
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_register_invalid_email_returns_422(self):
        client, engine = await self._make_client()
        async with client as c:
            r = await c.post("/api/auth/register", json={"email": "not-an-email", "password": "pass1234"})
        assert r.status_code == 422
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_login_valid_credentials_returns_token(self):
        client, engine = await self._make_client()
        async with client as c:
            await c.post("/api/auth/register", json={"email": "bob@test.com", "password": "hunter2!"})
            r = await c.post("/api/auth/login", data={"username": "bob@test.com", "password": "hunter2!"})
        assert r.status_code == 200
        assert "access_token" in r.json()
        assert r.json()["token_type"] == "bearer"
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_401(self):
        client, engine = await self._make_client()
        async with client as c:
            await c.post("/api/auth/register", json={"email": "carol@test.com", "password": "correct"})
            r = await c.post("/api/auth/login", data={"username": "carol@test.com", "password": "wrong"})
        assert r.status_code == 401
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_login_unknown_email_returns_401(self):
        client, engine = await self._make_client()
        async with client as c:
            r = await c.post("/api/auth/login", data={"username": "ghost@test.com", "password": "pass"})
        assert r.status_code == 401
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_me_with_valid_token_returns_user(self):
        client, engine = await self._make_client()
        async with client as c:
            await c.post("/api/auth/register", json={"email": "dave@test.com", "password": "pass1234"})
            login_r = await c.post("/api/auth/login", data={"username": "dave@test.com", "password": "pass1234"})
            token = login_r.json()["access_token"]
            r = await c.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["email"] == "dave@test.com"
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_me_without_token_returns_401(self):
        client, engine = await self._make_client()
        async with client as c:
            r = await c.get("/api/auth/me")
        assert r.status_code == 401
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_me_with_invalid_token_returns_401(self):
        client, engine = await self._make_client()
        async with client as c:
            r = await c.get("/api/auth/me", headers={"Authorization": "Bearer not.a.real.token"})
        assert r.status_code == 401
        await engine.dispose()


# ── Helpers for CRUD tests ────────────────────────────────────────────────────

async def _setup_crud_client():
    """Build a client + engine with auth + team + player + game routers."""
    from app.routes.auth import router as auth_router
    from app.routes.teams import router as teams_router
    from app.routes.players import router as players_router
    from app.routes.games import router as games_router

    engine = await build_engine()
    db_override = make_session_override(engine)
    app = make_app(auth_router, teams_router, players_router, games_router, db_override=db_override)
    return AsyncClient(app=app, base_url="http://test"), engine


async def _register_and_login(c: AsyncClient, email: str = "cap@crud.test", password: str = "Passw0rd!") -> dict:
    await c.post("/api/auth/register", json={"email": email, "password": password})
    r = await c.post("/api/auth/login", data={"username": email, "password": password})
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── TestCrudFlow ──────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestCrudFlow:
    """CRUD routes: teams → players → games → attendance."""

    @pytest.mark.asyncio
    async def test_create_team_returns_201(self):
        client, engine = await _setup_crud_client()
        async with client as c:
            headers = await _register_and_login(c)
            r = await c.post("/api/teams", json={"name": "Ice Wolves"}, headers=headers)
        assert r.status_code == 201
        assert r.json()["name"] == "Ice Wolves"
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_create_team_unauthenticated_returns_401(self):
        client, engine = await _setup_crud_client()
        async with client as c:
            r = await c.post("/api/teams", json={"name": "Ghost Team"})
        assert r.status_code == 401
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_list_teams_returns_captains_teams(self):
        client, engine = await _setup_crud_client()
        async with client as c:
            h1 = await _register_and_login(c, "cap1@test.com")
            h2 = await _register_and_login(c, "cap2@test.com")
            await c.post("/api/teams", json={"name": "Team A"}, headers=h1)
            await c.post("/api/teams", json={"name": "Team B"}, headers=h2)
            r = await c.get("/api/teams", headers=h1)
        assert r.status_code == 200
        names = [t["name"] for t in r.json()]
        assert "Team A" in names
        assert "Team B" not in names
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_add_player_to_team_returns_201(self):
        client, engine = await _setup_crud_client()
        async with client as c:
            headers = await _register_and_login(c)
            team_r = await c.post("/api/teams", json={"name": "Pucks"}, headers=headers)
            team_id = team_r.json()["id"]
            r = await c.post("/api/players", json={
                "name": "Alice Smith",
                "phone": "+16135550101",
                "team_id": team_id,
                "position_prefs": ["center", "wing"],
            }, headers=headers)
        assert r.status_code == 201
        assert r.json()["name"] == "Alice Smith"
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_list_roster_returns_players(self):
        client, engine = await _setup_crud_client()
        async with client as c:
            headers = await _register_and_login(c)
            team_r = await c.post("/api/teams", json={"name": "Bears"}, headers=headers)
            team_id = team_r.json()["id"]
            await c.post("/api/players", json={"name": "Bob", "phone": "+16135550102", "team_id": team_id}, headers=headers)
            await c.post("/api/players", json={"name": "Carol", "phone": "+16135550103", "team_id": team_id}, headers=headers)
            r = await c.get(f"/api/teams/{team_id}/players", headers=headers)
        assert r.status_code == 200
        names = [p["name"] for p in r.json()]
        assert "Bob" in names
        assert "Carol" in names
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_create_game_returns_201(self):
        client, engine = await _setup_crud_client()
        async with client as c:
            headers = await _register_and_login(c)
            r = await c.post("/api/games", json={
                "game_date": "2026-03-15",
                "game_time": "21:00:00",
                "location": "Arena North",
            }, headers=headers)
        assert r.status_code == 201
        assert r.json()["location"] == "Arena North"
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_get_game_not_found_returns_404(self):
        client, engine = await _setup_crud_client()
        async with client as c:
            headers = await _register_and_login(c)
            r = await c.get("/api/games/9999", headers=headers)
        assert r.status_code == 404
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_upsert_attendance_persists(self):
        client, engine = await _setup_crud_client()
        async with client as c:
            headers = await _register_and_login(c)
            team_r = await c.post("/api/teams", json={"name": "Stars"}, headers=headers)
            team_id = team_r.json()["id"]
            player_r = await c.post("/api/players", json={
                "name": "Dave", "phone": "+16135550104", "team_id": team_id,
            }, headers=headers)
            player_id = player_r.json()["id"]
            game_r = await c.post("/api/games", json={"game_date": "2026-04-01", "game_time": "20:00:00"}, headers=headers)
            game_id = game_r.json()["id"]

            r = await c.put(f"/api/games/{game_id}/attendance", json={
                "player_id": player_id, "status": "yes"
            }, headers=headers)
        assert r.status_code == 200
        assert r.json()["status"] == "yes"
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_duplicate_player_phone_returns_409(self):
        client, engine = await _setup_crud_client()
        async with client as c:
            headers = await _register_and_login(c)
            await c.post("/api/players", json={"name": "Eve", "phone": "+16135550105"}, headers=headers)
            r = await c.post("/api/players", json={"name": "Eve2", "phone": "+16135550105"}, headers=headers)
        assert r.status_code == 409
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_delete_team_returns_204(self):
        client, engine = await _setup_crud_client()
        async with client as c:
            headers = await _register_and_login(c)
            team_r = await c.post("/api/teams", json={"name": "ToDelete"}, headers=headers)
            team_id = team_r.json()["id"]
            r = await c.delete(f"/api/teams/{team_id}", headers=headers)
        assert r.status_code == 204
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_cannot_access_other_captains_team(self):
        client, engine = await _setup_crud_client()
        async with client as c:
            h1 = await _register_and_login(c, "owner@test.com")
            h2 = await _register_and_login(c, "other@test.com")
            team_r = await c.post("/api/teams", json={"name": "OwnerTeam"}, headers=h1)
            team_id = team_r.json()["id"]
            r = await c.get(f"/api/teams/{team_id}", headers=h2)
        assert r.status_code == 404
        await engine.dispose()


# ── TestSmsWebhook ────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestSmsWebhook:
    """Twilio inbound SMS webhook: signature validation, task dispatch."""

    def _make_app(self):
        from app.routes.sms import router
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.mark.asyncio
    async def test_valid_form_queues_celery_task(self):
        """POST with valid From+Body dispatches Celery task and returns TwiML."""
        app = self._make_app()
        with patch("app.routes.sms.process_inbound_sms") as mock_task:
            mock_task.delay = MagicMock()
            async with AsyncClient(app=app, base_url="http://test") as c:
                r = await c.post("/sms/webhook", data={"From": "+16135550101", "Body": "yes I'll be there"})
        assert r.status_code == 200
        assert "Response" in r.text
        mock_task.delay.assert_called_once_with(from_phone="+16135550101", body="yes I'll be there")

    @pytest.mark.asyncio
    async def test_missing_from_field_returns_400(self):
        """No From field → 400 Bad Request."""
        app = self._make_app()
        with patch("app.routes.sms.process_inbound_sms") as mock_task:
            mock_task.delay = MagicMock()
            async with AsyncClient(app=app, base_url="http://test") as c:
                r = await c.post("/sms/webhook", data={"Body": "hello"})
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_body_still_queues_task(self):
        """Empty Body is valid — still queues task (pipeline handles empty input)."""
        app = self._make_app()
        with patch("app.routes.sms.process_inbound_sms") as mock_task:
            mock_task.delay = MagicMock()
            async with AsyncClient(app=app, base_url="http://test") as c:
                r = await c.post("/sms/webhook", data={"From": "+16135550101", "Body": ""})
        assert r.status_code == 200
        mock_task.delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_twiml_xml_content_type(self):
        """Response Content-Type should be text/* (plain text TwiML)."""
        app = self._make_app()
        with patch("app.routes.sms.process_inbound_sms") as mock_task:
            mock_task.delay = MagicMock()
            async with AsyncClient(app=app, base_url="http://test") as c:
                r = await c.post("/sms/webhook", data={"From": "+16135550101", "Body": "hi"})
        assert "text/" in r.headers["content-type"]

    @pytest.mark.asyncio
    async def test_twilio_signature_skipped_when_auth_token_empty(self):
        """TWILIO_AUTH_TOKEN='' → skip validation, always accept."""
        app = self._make_app()
        with (
            patch("app.routes.sms.settings") as mock_settings,
            patch("app.routes.sms.process_inbound_sms") as mock_task,
        ):
            mock_settings.twilio_auth_token = ""
            mock_task.delay = MagicMock()
            async with AsyncClient(app=app, base_url="http://test") as c:
                r = await c.post("/sms/webhook", data={"From": "+16135550101", "Body": "test"})
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_twilio_signature_rejected_when_invalid(self):
        """TWILIO_AUTH_TOKEN set + bad signature → 403."""
        app = self._make_app()
        with (
            patch("app.routes.sms.settings") as mock_settings,
            patch("app.routes.sms.validate_twilio_signature", return_value=False),
            patch("app.routes.sms.process_inbound_sms") as mock_task,
        ):
            mock_settings.twilio_auth_token = "real_secret"
            mock_task.delay = MagicMock()
            async with AsyncClient(app=app, base_url="http://test") as c:
                r = await c.post(
                    "/sms/webhook",
                    data={"From": "+16135550101", "Body": "hi"},
                    headers={"X-Twilio-Signature": "bad_sig"},
                )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_twilio_signature_accepted_when_valid(self):
        """TWILIO_AUTH_TOKEN set + valid signature → 200."""
        app = self._make_app()
        with (
            patch("app.routes.sms.settings") as mock_settings,
            patch("app.routes.sms.validate_twilio_signature", return_value=True),
            patch("app.routes.sms.process_inbound_sms") as mock_task,
        ):
            mock_settings.twilio_auth_token = "real_secret"
            mock_task.delay = MagicMock()
            async with AsyncClient(app=app, base_url="http://test") as c:
                r = await c.post(
                    "/sms/webhook",
                    data={"From": "+16135550101", "Body": "hi"},
                    headers={"X-Twilio-Signature": "valid_sig"},
                )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_celery_task_receives_correct_args(self):
        """Task .delay() called with exactly the right From/Body values."""
        app = self._make_app()
        with patch("app.routes.sms.process_inbound_sms") as mock_task:
            mock_task.delay = MagicMock()
            async with AsyncClient(app=app, base_url="http://test") as c:
                await c.post("/sms/webhook", data={"From": "+12025559999", "Body": "need a sub Saturday"})
        mock_task.delay.assert_called_once_with(
            from_phone="+12025559999", body="need a sub Saturday"
        )

    @pytest.mark.asyncio
    async def test_twiml_ack_content(self):
        """The TwiML body is the expected empty-response XML."""
        app = self._make_app()
        with patch("app.routes.sms.process_inbound_sms") as mock_task:
            mock_task.delay = MagicMock()
            async with AsyncClient(app=app, base_url="http://test") as c:
                r = await c.post("/sms/webhook", data={"From": "+16135550101", "Body": "hi"})
        assert "<?xml" in r.text
        assert "<Response>" in r.text


# ── TestChatStream ────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestChatStream:
    """SSE chat streaming endpoint tests."""

    async def _make_client_with_token(self):
        from app.routes.auth import router as auth_router
        from app.routes.chat import router as chat_router

        engine = await build_engine()
        db_override = make_session_override(engine)
        app = make_app(auth_router, chat_router, db_override=db_override)
        client = AsyncClient(app=app, base_url="http://test")
        return client, engine

    async def _get_token(self, c: AsyncClient) -> str:
        await c.post("/api/auth/register", json={"email": "stream@test.com", "password": "passw0rd!"})
        r = await c.post("/api/auth/login", data={"username": "stream@test.com", "password": "passw0rd!"})
        return r.json()["access_token"]

    def _parse_sse(self, body: str) -> list[dict]:
        events = []
        for block in body.split("\n\n"):
            for line in block.splitlines():
                if line.startswith("data: "):
                    try:
                        events.append(json.loads(line[6:]))
                    except json.JSONDecodeError:
                        pass
        return events

    @pytest.mark.asyncio
    async def test_chat_stream_requires_captain_auth(self):
        """No token → 401 before any SSE events."""
        client, engine = await self._make_client_with_token()
        async with client as c:
            r = await c.post("/api/chat/stream", json={"input": "hello", "context": {}})
        assert r.status_code == 401
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_chat_stream_returns_event_stream_content_type(self):
        """Content-Type must be text/event-stream."""
        async def _mock_stream(raw_input, context, db):
            yield {"type": "done", "text_for_user": "ok", "mutations": []}

        client, engine = await self._make_client_with_token()
        with patch("app.routes.chat.run_pipeline_stream", side_effect=_mock_stream):
            async with client as c:
                token = await self._get_token(c)
                r = await c.post(
                    "/api/chat/stream",
                    json={"input": "hi", "context": {}},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert "text/event-stream" in r.headers.get("content-type", "")
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_chat_stream_yields_answer_token_events(self):
        """answer_token events from pipeline appear in SSE stream."""
        async def _mock_stream(raw_input, context, db):
            yield {"type": "answer_token", "text": "Hello"}
            yield {"type": "answer_token", "text": " world"}
            yield {"type": "done", "text_for_user": "Hello world", "mutations": []}

        client, engine = await self._make_client_with_token()
        with patch("app.routes.chat.run_pipeline_stream", side_effect=_mock_stream):
            async with client as c:
                token = await self._get_token(c)
                r = await c.post(
                    "/api/chat/stream",
                    json={"input": "hi", "context": {}},
                    headers={"Authorization": f"Bearer {token}"},
                )
        events = self._parse_sse(r.text)
        token_texts = [e["text"] for e in events if e.get("type") == "answer_token"]
        assert "Hello" in token_texts
        assert " world" in token_texts
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_chat_stream_yields_done_event(self):
        """done event is present and has text_for_user."""
        async def _mock_stream(raw_input, context, db):
            yield {"type": "done", "text_for_user": "The final answer.", "mutations": []}

        client, engine = await self._make_client_with_token()
        with patch("app.routes.chat.run_pipeline_stream", side_effect=_mock_stream):
            async with client as c:
                token = await self._get_token(c)
                r = await c.post(
                    "/api/chat/stream",
                    json={"input": "q", "context": {}},
                    headers={"Authorization": f"Bearer {token}"},
                )
        events = self._parse_sse(r.text)
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(done_events) == 1
        assert done_events[0]["text_for_user"] == "The final answer."
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_chat_stream_yields_tool_events(self):
        """tool_start and tool_result events pass through."""
        async def _mock_stream(raw_input, context, db):
            yield {"type": "tool_start", "name": "get_roster", "input": {"team_id": 7}}
            yield {"type": "tool_result", "name": "get_roster", "result": []}
            yield {"type": "done", "text_for_user": "Done.", "mutations": []}

        client, engine = await self._make_client_with_token()
        with patch("app.routes.chat.run_pipeline_stream", side_effect=_mock_stream):
            async with client as c:
                token = await self._get_token(c)
                r = await c.post(
                    "/api/chat/stream",
                    json={"input": "roster?", "context": {"team_id": 7}},
                    headers={"Authorization": f"Bearer {token}"},
                )
        events = self._parse_sse(r.text)
        types = [e.get("type") for e in events]
        assert "tool_start" in types
        assert "tool_result" in types
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_chat_stream_yields_error_event_on_pipeline_failure(self):
        """If pipeline yields error event, it propagates to client."""
        async def _mock_stream(raw_input, context, db):
            yield {"type": "error", "message": "Something went wrong."}

        client, engine = await self._make_client_with_token()
        with patch("app.routes.chat.run_pipeline_stream", side_effect=_mock_stream):
            async with client as c:
                token = await self._get_token(c)
                r = await c.post(
                    "/api/chat/stream",
                    json={"input": "fail", "context": {}},
                    headers={"Authorization": f"Bearer {token}"},
                )
        events = self._parse_sse(r.text)
        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) == 1
        assert "went wrong" in error_events[0]["message"]
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_chat_stream_sets_channel_dashboard_in_context(self):
        """Route injects channel='dashboard' into context before calling pipeline."""
        captured_context: dict = {}

        async def _mock_stream(raw_input, context, db):
            captured_context.update(context)
            yield {"type": "done", "text_for_user": "ok", "mutations": []}

        client, engine = await self._make_client_with_token()
        with patch("app.routes.chat.run_pipeline_stream", side_effect=_mock_stream):
            async with client as c:
                token = await self._get_token(c)
                await c.post(
                    "/api/chat/stream",
                    json={"input": "hello", "context": {}},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert captured_context.get("channel") == "dashboard"
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_chat_stream_forwards_context_fields(self):
        """team_id and other context fields from request body are forwarded."""
        captured_context: dict = {}

        async def _mock_stream(raw_input, context, db):
            captured_context.update(context)
            yield {"type": "done", "text_for_user": "ok", "mutations": []}

        client, engine = await self._make_client_with_token()
        with patch("app.routes.chat.run_pipeline_stream", side_effect=_mock_stream):
            async with client as c:
                token = await self._get_token(c)
                await c.post(
                    "/api/chat/stream",
                    json={"input": "hi", "context": {"team_id": 42}},
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert captured_context.get("team_id") == 42
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_chat_stream_non_captain_returns_403(self):
        """User without is_captain flag cannot use the chat stream."""
        from app.routes.auth import router as auth_router
        from app.routes.chat import router as chat_router
        from app.auth import require_captain
        from fastapi import FastAPI, HTTPException, status

        engine = await build_engine()
        db_override = make_session_override(engine)

        # Override require_captain to raise 403
        async def deny_non_captain():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Captains only")

        app = make_app(auth_router, chat_router, db_override=db_override)
        app.dependency_overrides[require_captain] = deny_non_captain

        async with AsyncClient(app=app, base_url="http://test") as c:
            r = await c.post(
                "/api/chat/stream",
                json={"input": "hello", "context": {}},
                headers={"Authorization": "Bearer fake_token"},
            )
        assert r.status_code == 403
        await engine.dispose()
