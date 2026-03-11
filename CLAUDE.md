# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env  # then fill in values

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "description"  # generate new migration

# Run API server
uvicorn app.main:app --reload --port 8000

# Run background worker (separate terminal)
python -m app.jobs.scheduler
```

## Architecture

### Two-process deployment
The app runs as two separate processes (see `Procfile`):
- **web**: FastAPI via uvicorn — handles HTTP requests
- **worker**: `app/jobs/scheduler.py` — standalone APScheduler process that checks topics every hour

The scheduler runs independently without any connection to the FastAPI process. Both share the same PostgreSQL database.

### Topic lifecycle
The two-step topic creation flow is central:
1. `POST /topics/analyze` — fetches article content (Tavily Extract → httpx/BS4 fallback), calls OpenAI to return 1–3 topic proposals; **nothing is saved**
2. `POST /topics` (confirm) — re-fetches content, generates search keywords, extracts initial facts, then saves Topic + Facts to DB

The background worker runs `check_topic()` from `services/topic_checker.py` which: searches via Tavily → AI filters relevant results → AI extracts new facts vs known facts → saves Fact records → deducts 1 credit → sends email notification.

### AI pipeline
All prompts are `.txt` files in `app/prompts/`. They are loaded at call time (not cached). All OpenAI calls use `response_format={"type": "json_object"}` and must return valid JSON. The `compare_facts.txt` prompt is reused for both initial fact extraction (with `KNOWN FACTS: []`) and subsequent comparisons.

Tenacity retry config: OpenAI calls use 3 attempts with exponential backoff (2–10s); Tavily calls use 2 attempts (2–8s).

### Auth
JWT stored in httpOnly cookie named `access_token`. The `get_current_user` dependency is in `app/api/deps.py`. Magic link tokens are stored in-memory (dict) — not suitable for multi-process production deployments.

### Error responses
Always use `{"detail": "message"}` with `X-Error-Code` header for machine-readable codes (e.g., `FETCH_FAILED`, `NO_CREDITS`, `ANALYSIS_FAILED`).

## Key conventions
- All code, comments, variable names, and AI prompts in **English**
- Type hints everywhere; async FastAPI endpoints
- Pydantic v2 schemas in `app/schemas/`; SQLAlchemy 2.0 models in `app/models/`
- CORS restricted to `settings.APP_URL` only
- Rate limiting via `slowapi` on auth endpoints
- Do not log API keys or personal data
