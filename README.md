# Owlo API

Backend for Owlo — a service that tracks how a specific news story develops over time, instead of dumping every new article about a broad topic into your feed.

## The idea

You paste in a link to an article. Owlo doesn't just save it — it reads it, and an AI pass identifies the *specific* story being reported, not the broad topic. "Sony player class-action over digital sales monopolization" gets tracked, not just "lawsuits against Sony" — because the latter would surface hundreds of unrelated future articles. Owlo then periodically re-searches the web for that exact story and only notifies you when it finds a genuinely **new fact** — never a duplicate, a reworded rewrite of the same news, or an unrelated result that happens to match the same keywords.

That "only new facts" constraint is the core product bet, and it's a harder problem than it sounds: most sites republish the same wire story under different headlines, and a naive keyword search treats every rewrite as new. The fact-comparison step in `services/topic_checker.py` runs each candidate fact against everything already known about a topic and keeps only what's genuinely incremental — filtering out duplicates, paraphrases, and opinion pieces about facts that are already known.

## How a topic moves through the system

1. **Analyze** (`POST /topics/analyze`) — fetches the article, asks an LLM to propose 1–3 distinct topic candidates (title + description), and returns them without saving anything. If the article is unambiguous, there's just one candidate.
2. **Confirm** (`POST /topics`) — re-fetches the content for the chosen candidate, generates search keywords (in the source language and in English), extracts the initial facts, and persists the Topic + Facts.
3. **Background checking** — a separate worker process wakes up hourly, finds topics due for a check, searches the web (Tavily) using the topic's keywords, and asks the AI to compare what it found against the facts already on file. Genuinely new facts get saved and trigger an email notification; everything else is discarded.

## Stack

- **Python 3.12** / **FastAPI**, async endpoints throughout
- **PostgreSQL** via SQLAlchemy 2.0, migrations with Alembic
- **Tavily** for web search and content extraction
- **OpenAI** (`gpt-4.1-nano`) for topic extraction, keyword generation, and fact comparison — all structured JSON responses
- Auth via Google OAuth or passwordless magic links, JWT in an httpOnly cookie
- Runs as two processes (`Procfile`): a FastAPI web process and a standalone APScheduler worker that share one database

## Running locally

```bash
python -m venv venv
source venv/bin/activate      # venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env           # fill in the values below

alembic upgrade head
uvicorn app.main:app --reload --port 8000

# separate terminal — the periodic topic-checking worker
python -m app.jobs.scheduler
```

### Environment variables

```env
DATABASE_URL=postgresql://user:password@localhost:5432/pulsefeed
SECRET_KEY=random-secret-key-for-jwt

TAVILY_API_KEY=tvly-xxxxx
OPENAI_API_KEY=sk-xxxxx
OPENAI_MODEL=gpt-4.1-nano

GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxxxx

EMAIL_PROVIDER=resend         # or "smtp"
RESEND_API_KEY=re_xxxxx
EMAIL_FROM=noreply@example.com

APP_URL=https://app.example.com
API_URL=https://api.example.com
COOKIE_DOMAIN=.example.com
```

## API surface

```
POST   /auth/google           Google OAuth callback → sets auth cookie
POST   /auth/magic-link       sends a magic link by email
POST   /auth/verify           verifies a magic link token → sets auth cookie
GET    /auth/me                current user
POST   /auth/logout            invalidates the session

POST   /topics/analyze        propose topic candidates for a URL (nothing saved)
POST   /topics                confirm a candidate and start tracking it
GET    /topics                 the user's topics, flagged with has_update
GET    /topics/:id             a topic with its full fact timeline
PATCH  /topics/:id             change check frequency / pause / archive
DELETE /topics/:id             remove a topic
POST   /topics/:id/check      force an immediate check (costs one credit)
POST   /topics/:id/mark-read  clear the has_update flag

GET    /users/settings        user preferences
PATCH  /users/settings        update preferences
GET    /users/credits          remaining credits and usage history

GET    /notifications          the user's notifications
POST   /notifications/mark-read
```

## Data model

- **User** — email, optional Google id, UI language, default check interval, remaining credits
- **Topic** — the tracked story: source URL, AI-assigned title/description, search keywords, check interval, `has_update` flag, status (active/paused/archived)
- **Fact** — one atomic piece of information tied to a topic, with its source and discovery date, flagged as `is_initial` (from the original article) or discovered later
- **CheckResult** — an audit record of one background check: queries used, sources found, new facts found, credits spent
- **Notification** — new-facts / topic-added / low-credits alerts sent to the user

## Deployment

Ships as two Dokku processes on one PostgreSQL database:

```
web:    uvicorn app.main:app --host 0.0.0.0 --port $PORT
worker: python -m app.jobs.scheduler
```
