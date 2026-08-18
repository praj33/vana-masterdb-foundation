# ============================================================
# Dockerfile — VANA MasterDB Foundation API
# Target: PostgreSQL + PostGIS VM (production)
# Local dev: docker-compose.yml (SQLite fallback)
# ============================================================

FROM python:3.11.7-slim AS builder
WORKDIR /app

# gcc needed for psycopg2 source builds on non-binary wheels
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- runtime image ----
FROM python:3.11.7-slim
WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

# Copy all application source
COPY . .

EXPOSE 8000

# Run DB migration then start the API server.
# VANA_DATABASE_URL must be provided at runtime via env / docker-compose.
CMD ["sh", "-c", "python init_db.py && uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
