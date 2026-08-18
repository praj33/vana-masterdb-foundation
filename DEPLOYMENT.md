# VANA MasterDB Foundation — Deployment Runbook

> **Commit**: `92a37b337df1fb1d4b8565ada47656d182771cdf`
> **Repo**: `https://github.com/praj33/vana-masterdb-foundation.git`
> **Purpose**: PostgreSQL + PostGIS VM deployment for Group 3 → VANA observation flow end-to-end validation.

---

## What This Deploys

| Component | Image / Source |
|---|---|
| **PostgreSQL 16 + PostGIS 3.4** | `postgis/postgis:16-3.4` (official Docker Hub image) |
| **VANA MasterDB API** | Built from this repo via `Dockerfile` |

The API exposes:
- `POST /observations` — ingest a Group 3 observation with idempotency
- `GET /observations/{id}` — retrieve a persisted observation
- `GET /health` — health probe
- `GET /docs` — Swagger UI

---

## VM Requirements

| Requirement | Minimum |
|---|---|
| OS | Ubuntu 22.04 LTS (or any Linux with Docker) |
| CPU | 2 vCPU |
| RAM | 2 GB |
| Disk | 20 GB |
| Docker Engine | ≥ 24 |
| Docker Compose plugin | ≥ 2.24 |
| Open port | `8010` (or whatever `VANA_API_PORT` is set to) |

---

## Step-by-Step Deployment

### 1. Clone the repository

```bash
git clone https://github.com/praj33/vana-masterdb-foundation.git
cd vana-masterdb-foundation
git checkout 92a37b337df1fb1d4b8565ada47656d182771cdf
```

### 2. Create the `.env` file

```bash
cp .env.example .env
nano .env   # or vim .env
```

Fill in at minimum:
```
POSTGRES_PASSWORD=<a strong password — do not leave as CHANGE_ME>
```

The defaults (`POSTGRES_USER=vana`, `POSTGRES_DB=vana_masterdb`, `VANA_API_PORT=8010`) are fine for most deployments.

### 3. Make the deployment scripts executable

```bash
chmod +x deployment/deploy.sh
chmod +x deployment/healthcheck.sh
chmod +x deployment/run_e2e_test.sh
```

### 4. Deploy

```bash
./deployment/deploy.sh
```

This command:
1. Validates `.env` exists and Docker is available
2. Builds the VANA API Docker image
3. Starts `vana-db` (PostgreSQL + PostGIS) and waits for it to be healthy
4. Starts `vana-api`; the container runs `python init_db.py` on boot which applies `migrations/0001_init.sql` (idempotent — safe to re-run)
5. Polls until both containers report `healthy` (up to 90 s)
6. Prints the API URL

### 5. Verify health

```bash
./deployment/healthcheck.sh

# Or directly:
curl http://localhost:8010/health
```

Expected:
```json
{"status": "healthy", "service": "VANA MasterDB Observation API", "version": "1.0.0"}
```

---

## End-to-End Idempotency Acceptance Test (0 → 1 → 1)

Run the canonical acceptance test:

```bash
./deployment/run_e2e_test.sh
```

Or against a remote host:

```bash
./deployment/run_e2e_test.sh http://<VM_PUBLIC_IP>:8010
```

### What the test proves

| Round | Action | Expected HTTP | Expected body status | DB count |
|---|---|---|---|---|
| 1 | First submission (new observation) | `201` | `ACCEPTED` | **1** |
| 2 | Exact replay (same key + same payload) | `200` | `IDEMPOTENT_REPLAY` | **1** |
| 3 | Same key, mutated payload (conflict) | `409` | `IDEMPOTENCY_CONFLICT` | **1** |
| 4 | GET retrieval | `200` | `RETRIEVED` | — |

**0 → 1 → 1 is proven when all four checks show `[PASS]`.**

---

## Manual curl Equivalent

If you want to run the acceptance scenario manually with your own fixture:

```bash
# Round 1 — first submission
curl -X POST http://localhost:8010/observations \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: MY-IDEM-KEY-001" \
  -d @sample_mission_package.json   # use a single observation object, not the full package

# Round 2 — exact replay (same command)
curl -X POST http://localhost:8010/observations \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: MY-IDEM-KEY-001" \
  -d @sample_mission_package.json

# Round 3 — same key, changed payload
curl -X POST http://localhost:8010/observations \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: MY-IDEM-KEY-001" \
  -d '{"observation_id": "TC-Z03-F02-LIDAR-OBS001", "measurement": 99.9, ...}'
```

---

## Managing the Stack

```bash
# View logs
docker compose -f docker-compose.production.yml logs -f vana-api
docker compose -f docker-compose.production.yml logs -f vana-db

# Stop everything
docker compose -f docker-compose.production.yml down

# Stop and wipe the database volume (full reset)
docker compose -f docker-compose.production.yml down -v

# Restart only the API (e.g. after a code update)
docker compose -f docker-compose.production.yml build vana-api
docker compose -f docker-compose.production.yml up -d vana-api
```

---

## How the Schema Migration Works

`init_db.py` is run automatically by the Docker container on startup via the `CMD` in `Dockerfile`:

```
python init_db.py && uvicorn api.main:app ...
```

It reads `VANA_DATABASE_URL` and applies `migrations/0001_init.sql` which:
- Creates the PostGIS extension
- Creates all tables: `schema_version`, `source`, `dataset`, `geo_location`, `observation`, `field_observation_meta`, `measurement`, `raw_artifact`, `processing_run`, `provenance`, `idempotency_record`
- Tracks itself in `_migrations_log` — re-running is a no-op

**You do not need to run `init_db.py` manually on the VM** — `deploy.sh` handles everything.

---

## Connecting Directly to PostgreSQL (for inspection)

```bash
# From the VM host
docker exec -it vana_db psql -U vana -d vana_masterdb

# Useful queries after the e2e test
SELECT count(*) FROM observation;
SELECT * FROM idempotency_record;
SELECT version, applied_at FROM schema_version ORDER BY applied_at;
SELECT ST_AsText(geom), place_name FROM geo_location;
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `vana_db` never reaches `healthy` | Wrong `POSTGRES_PASSWORD` in `.env` | Check `.env`, `docker compose down -v`, re-deploy |
| `vana_api` crashes on startup | `VANA_DATABASE_URL` not reachable | Check DB container is healthy first; check network |
| `HTTP 400 REJECTED` on POST | Observation payload fails Group 3 schema validation | Check `observation.schema.json` required fields |
| `HTTP 409 DUPLICATE` (no idempotency key) | Observation ID already exists | Normal — send an `Idempotency-Key` header for replay support |
| PostGIS extension missing | Using plain Postgres image (not `postgis/postgis`) | Use `postgis/postgis:16-3.4` as specified in compose |

---

## File Reference

| File | Purpose |
|---|---|
| [`Dockerfile`](./Dockerfile) | Multi-stage image build |
| [`docker-compose.yml`](./docker-compose.yml) | Local dev (SQLite, no Postgres needed) |
| [`docker-compose.production.yml`](./docker-compose.production.yml) | VM deployment (PostgreSQL + PostGIS) |
| [`.env.example`](./.env.example) | Environment variable template |
| [`deployment/deploy.sh`](./deployment/deploy.sh) | One-command VM deploy |
| [`deployment/run_e2e_test.sh`](./deployment/run_e2e_test.sh) | 0→1→1 idempotency acceptance test |
| [`deployment/healthcheck.sh`](./deployment/healthcheck.sh) | Health probe script |
| [`migrations/0001_init.sql`](./migrations/0001_init.sql) | PostgreSQL + PostGIS schema (v0.4) |
| [`init_db.py`](./init_db.py) | Migration runner (SQLite + Postgres) |
| [`api/main.py`](./api/main.py) | FastAPI application |
| [`api/persistence.py`](./api/persistence.py) | Observation persistence + idempotency logic |
| [`api/db.py`](./api/db.py) | DB connection abstraction (SQLite / Postgres) |
| [`sample_mission_package.json`](./sample_mission_package.json) | Group 3 synthetic fixture |
| [`tests/test_api.py`](./tests/test_api.py) | Pytest suite (SQLite-backed, no VM needed) |
