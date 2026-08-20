# Britannia RFID Platform — Unified Backend

Single FastAPI backend serving all four portals — **Super Admin**, **Vendor**, **Warehouse**,
**Retail** — against one PostgreSQL database. Consolidated from three previously-separate
codebases (`Backend-WH-Retail`, `brfid-portal-backend/super-admin-backend`,
`brfid-portal-backend/vms-backend`); see the merge plan for the full rationale and per-table
schema reconciliation decisions behind this project's shape.

## Stack

FastAPI · SQLAlchemy 2.0 (sync, psycopg2) · Alembic · Pydantic v2 · PostgreSQL 16 · SeaweedFS
(file storage) · pytest.

## Architecture

Modular monolith, `router → service → repository → model` throughout:

```
app/
├── core/            # config, database, security, exceptions, logging
├── api/v1/{auth,super_admin,vendor,warehouse,retail}/
├── models/, schemas/, services/, repositories/
├── dependencies/, middleware/, utils/, constants/
```

Every route is namespaced by portal under `/api/v1/{auth,super-admin,vendor,warehouse,retail}`.
Auth, RBAC (`require_portal`/`require_role`), the database session, and all cross-cutting
middleware are shared — no portal has its own copy of any of these.

## Database

Postgres runs **natively** on the host (a Windows PostgreSQL 18 service on port 5433 — port
5432 was already in use), not in a container. Set up once:

```
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -p 5433 -c "CREATE ROLE brfid_user LOGIN PASSWORD 'brfid_password';"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -p 5433 -c "CREATE DATABASE brfid_platform OWNER brfid_user;"
& "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h localhost -p 5433 -c "CREATE DATABASE brfid_platform_pytest OWNER brfid_user;"
```

`docker-compose.yml` keeps a commented-out `db` service if you ever want to switch back to a
Dockerized Postgres instead — uncomment it, set `DATABASE_PORT=5432` in `.env`, and point
`DATABASE_HOST` at `db` (or `host.docker.internal` if the api itself runs in Docker while
Postgres runs natively, as configured by default).

## Running locally

```
python -m venv .venv && .venv\Scripts\activate
python -m pip install -r requirements\dev.txt
python scripts\run_alembic.py upgrade head
python scripts\seed.py
python -m uvicorn app.main:app --reload
```

Use `python scripts\run_alembic.py <args>` instead of a bare `alembic` command for local/Windows
development — this avoids two problems: this Alembic version has no `-m` support, and this
machine's Application Control policy blocks standalone `.exe` files (`alembic.exe`/`pip.exe`).

### With Docker (api + SeaweedFS only — Postgres stays native)

```
docker compose up
```

The `api` container reaches the native Postgres via `host.docker.internal:5433` and runs
migrations automatically on start. API docs at `http://localhost:8000/docs`.

## Tests

```
pytest
```

Runs against a real Postgres database (`TEST_DATABASE_URL`), with each test wrapped in a
SAVEPOINT that's rolled back afterward — no mocking of the database layer.
