# ── Stage 1: base ─────────────────────────────────────────────────────────────
# Shared system dependencies and non-root user setup.
FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# ── Stage 2: deps ─────────────────────────────────────────────────────────────
# Install Python packages into an isolated prefix so the runtime stage stays lean.
FROM base AS deps

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --prefix=/install

# ── Stage 3: runtime ──────────────────────────────────────────────────────────
FROM base AS runtime

# Copy installed packages from deps stage
COPY --from=deps /install /usr/local

# Copy application source
COPY app/ ./app/

# Download spaCy model (needed at import time by the preprocess stage)
RUN python -m spacy download en_core_web_sm

# Switch to non-root user
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use 2 workers in production; override via CMD in docker-compose for dev
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
