"""
Locust load test for Phase 11.

Simulates two user classes:
  - SmsWebhookUser:   Hammers POST /sms/webhook (target: 10 req/s sustained)
  - DashboardApiUser: Exercises authenticated REST API endpoints

Run against a live backend:
    docker compose up postgres redis -d
    uvicorn app.main:app --reload --port 8000
    locust -f tests/locustfile.py --headless -u 20 -r 5 --run-time 60s --host http://localhost:8000

Target SLOs:
  - p95 latency < 500ms for /sms/webhook
  - p95 latency < 300ms for CRUD reads
  - Error rate < 1%

Note: the pipeline stages call external services (Anthropic, Qdrant, Ollama).
In a real load test environment, use stubs/mocks for those services.
The load test here exercises the FastAPI routing layer, middleware, DB pooling,
and rate limiter — not LLM inference throughput.
"""
from locust import HttpUser, between, task


class SmsWebhookUser(HttpUser):
    """
    Simulates inbound SMS traffic from Twilio.

    The webhook is fire-and-forget (returns immediately, queues a Celery task),
    so latency should be < 50ms in a healthy system.
    """

    # Wait 50–200ms between requests → ~5–20 req/s per spawned user
    wait_time = between(0.05, 0.2)

    @task(4)
    def inbound_attendance_sms(self):
        """Typical captain attendance confirmation."""
        self.client.post(
            "/sms/webhook",
            data={"From": "+16135550101", "Body": "yes I'll be there Tuesday"},
            name="/sms/webhook [attendance]",
        )

    @task(2)
    def inbound_roster_query(self):
        """Roster query via SMS."""
        self.client.post(
            "/sms/webhook",
            data={"From": "+16135550102", "Body": "who plays center?"},
            name="/sms/webhook [query]",
        )

    @task(1)
    def health_check(self):
        """Lightweight health probe — validates the app is up."""
        self.client.get("/health", name="/health")


class DashboardApiUser(HttpUser):
    """
    Simulates a captain using the web dashboard.

    Logs in on startup, then exercises CRUD and pipeline endpoints.
    """

    wait_time = between(0.1, 0.5)

    def on_start(self):
        """Register + login to obtain a JWT token."""
        import random
        email = f"load_user_{random.randint(1, 10000)}@load.test"
        password = "LoadTest123!"

        # Register (may 409 if already exists — that's fine)
        self.client.post(
            "/api/auth/register",
            json={"email": email, "password": password},
            name="/api/auth/register",
        )

        r = self.client.post(
            "/api/auth/login",
            data={"username": email, "password": password},
            name="/api/auth/login",
        )
        token = r.json().get("access_token", "") if r.status_code == 200 else ""
        self.headers = {"Authorization": f"Bearer {token}"}
        self.team_id = None

        if token:
            # Create a team once per user session
            tr = self.client.post(
                "/api/teams",
                json={"name": "Load Test Team"},
                headers=self.headers,
                name="/api/teams [create]",
            )
            if tr.status_code == 201:
                self.team_id = tr.json().get("id")

    @task(3)
    def list_teams(self):
        self.client.get("/api/teams", headers=self.headers, name="/api/teams [list]")

    @task(2)
    def list_games(self):
        self.client.get("/api/games", headers=self.headers, name="/api/games [list]")

    @task(2)
    def list_players(self):
        if self.team_id:
            self.client.get(
                f"/api/teams/{self.team_id}/players",
                headers=self.headers,
                name="/api/teams/{id}/players",
            )

    @task(1)
    def get_current_user(self):
        self.client.get("/api/auth/me", headers=self.headers, name="/api/auth/me")
