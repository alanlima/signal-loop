# SignalLoop

Minimal Django skeleton for the SignalLoop MVP. The landing endpoint at `/`
returns HTTP 200 with an empty body, so a blank browser page is expected.

## Local setup

Install Python 3.12 and uv, then run these commands from the repository root:

```powershell
uv sync --locked
uv run python manage.py check
uv run python manage.py runserver
```

Open http://127.0.0.1:8000/ and press Ctrl+C to stop the server.
`uv sync` also installs dependencies; `--locked` verifies that `pyproject.toml`
matches the committed `uv.lock` for reproducible setup. uv creates `.venv`
automatically, so manual activation is unnecessary.

## Tests

Run the entire suite:

```powershell
uv run pytest
```

Run only the landing endpoint test:

```powershell
uv run pytest tests/test_home.py
```

The test uses Django's built-in test client through pytest. No database setup,
migrations, PostgreSQL, Redis, or external services are needed for this skeleton.
Database-backed tests will need database lifecycle configuration when models
are introduced.

Settings are for local development only: debug mode is enabled and the secret
key is a public development placeholder. Production settings and service
configuration belong to later tasks.
