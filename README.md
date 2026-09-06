# SignalLoop

Minimal Django skeleton for the SignalLoop MVP. The landing endpoint at `/`
returns HTTP 200 with an empty body, so a blank browser page is expected.

## Local setup

Prerequisites: Python 3.12+, uv, and Docker with Compose v2.20+ (or v5).
On Windows, start Docker Desktop with Linux containers. Run these commands
from the repository root in PowerShell:

```powershell
uv sync --locked
Copy-Item .env.example .env
```

Edit `.env` and supply a unique, disposable `POSTGRES_PASSWORD`. The example
deliberately contains no password. A generated hex string avoids dotenv
quoting/interpolation issues. Do not overwrite an existing `.env` on repeat
setup. Real `.env` and `.env.*` files are ignored; only `.env.example` is tracked.

```powershell
docker compose up -d --wait --wait-timeout 120
docker compose ps
$env:UV_ENV_FILE = '.env'
uv run python manage.py migrate
uv run python manage.py check
docker compose exec -T redis redis-cli ping
uv run python manage.py runserver
```

Both containers should show `healthy`, Django check should report no issues,
and Redis should return `PONG`. Open http://127.0.0.1:8000/ and press Ctrl+C
to stop Django. The skeleton has no application migrations yet; `migrate`
still connects to PostgreSQL.

Compose reads `.env` automatically. Django reads the process environment;
`UV_ENV_FILE` tells uv to load `.env` for each `uv run` in this shell. Set it
again in a new shell, or use `uv run --env-file .env python manage.py check`
(and the same option for migrate/runserver). Exported variables take precedence
over `.env`; clear stale overrides if settings do not match.

`uv sync` also installs dependencies; `--locked` verifies that `pyproject.toml`
matches the committed `uv.lock` for reproducible setup. uv creates `.venv`
automatically, so manual activation is unnecessary.

## Services and readiness

| Service | Pinned image | Default host port | Readiness | Storage |
| --- | --- | --- | --- | --- |
| PostgreSQL | `postgres:18.3-bookworm` | `127.0.0.1:5432` | `pg_isready`, every 2 seconds | Named `postgres_data` volume at `/var/lib/postgresql` |
| Redis | `redis:8.2.4-bookworm` | `127.0.0.1:6379` | `redis-cli ping`, every 2 seconds | Disposable; snapshots and append-only persistence disabled |

Health checks time out after 3 seconds, with 30 retries; PostgreSQL gets a
10-second initialization grace period. Patch versions are pinned in
`compose.yaml`; upgrades are explicit edits. The PostgreSQL volume layout
follows the [official PostgreSQL 18 image](https://hub.docker.com/_/postgres).

All settings in `.env.example` are required. `POSTGRES_DB` and `POSTGRES_USER`
accept lowercase letters, digits and underscores, start with a letter or
underscore, and have a 63-character limit. Hosts must be `127.0.0.1` or
`localhost`. Ports must be 1–65535. `REDIS_DB` selects logical database 0–15.
For port conflicts, change `POSTGRES_PORT` or `REDIS_PORT` in `.env`, rerun
Compose, and restart Django. Internal container ports remain 5432 and 6379.
Redis has no authentication and is exposed only on the host loopback interface.

`manage.py check`, `migrate`, and runserver's normal preflight verify PostgreSQL
with an authenticated `SELECT 1` and Redis with `SELECT`/`PING` against the
configured host ports. Connection attempts have a 3-second timeout. The Redis
probe uses the [RESP interface](https://redis.io/docs/latest/develop/reference/protocol-spec/);
worker/client integration belongs to a later task.

## Shutdown and disposable data reset

Normal shutdown preserves PostgreSQL data:

```powershell
docker compose down
```

Next time, `docker compose up -d --wait` reuses the volume. Redis data is
disposable across container recreation.

**Reset only when you intend to permanently remove this Compose project's
disposable development database.** This is separate from normal shutdown:

```powershell
docker compose down --volumes
docker compose up -d --wait --wait-timeout 120
uv run --env-file .env python manage.py migrate
```

## Troubleshooting

- Docker engine unavailable: start Docker Desktop with Linux containers, then
  retry `docker compose up -d --wait`.
- Missing/invalid settings: Django names the variable to fix without echoing its
  value. Fill `.env` and use `UV_ENV_FILE` or `--env-file .env`.
- `signal_loop.E001`: PostgreSQL is unavailable or credentials do not match.
  Check `docker compose ps`, port overrides, and `POSTGRES_*`. Initialization
  variables only apply to an empty volume; changing `.env` does not change an
  existing database's password. Restore the original settings, or explicitly
  reset disposable data using the commands above.
- `signal_loop.E002`: Redis is unavailable or its response is invalid. Check
  `docker compose ps`, `REDIS_*`, and `docker compose exec -T redis redis-cli ping`.
- Service probes suppress raw driver/server errors, passwords and credential
  URLs. Do not share `.env`, Docker inspection output, or resolved Compose
  configuration: these can contain credentials.

## Tests

Run the entire suite:

```powershell
uv run pytest
```

Run only the landing endpoint test:

```powershell
uv run pytest tests/test_home.py
```

Tests use Django's test client, synthetic environment settings and simulated
service failures; no running services are needed. Live integration checks are
the startup, migration, readiness and persistence steps above.
Database-backed tests will need database lifecycle configuration when models
are introduced.

Settings are for local development only: debug mode is enabled and the secret
key is a public development placeholder. Production settings and service
configuration belong to later tasks.
