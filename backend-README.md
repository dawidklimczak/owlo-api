# PulseFeed Backend

Backend API dla aplikacji PulseFeed — serwisu do śledzenia rozwoju konkretnych newsów i tematów w czasie.

## Opis projektu

PulseFeed pozwala użytkownikom dodawać artykuły/newsy, a następnie automatycznie śledzi rozwój danego tematu. Użytkownik wkleja URL artykułu, AI analizuje treść i identyfikuje konkretny temat do śledzenia (np. "Pozew zbiorowy graczy przeciwko Sony o monopolizację sprzedaży cyfrowej", nie ogólnie "pozwy przeciwko Sony"). System okresowo sprawdza czy pojawiły się nowe informacje i powiadamia użytkownika tylko wtedy, gdy odkryje nowe fakty — nie duplikaty ani przepisane newsy.

## Stack technologiczny

- **Python 3.12+**
- **FastAPI** — framework API
- **PostgreSQL** — baza danych
- **SQLAlchemy** — ORM
- **Alembic** — migracje bazy danych
- **Tavily API** — wyszukiwanie w internecie
- **OpenAI API (GPT-4.1-nano)** — analiza artykułów, ekstrakcja tematów, porównywanie faktów
- **APScheduler** lub **Celery + Redis** — background jobs do okresowego sprawdzania tematów
- **Resend** lub **SMTP** — wysyłka emaili (magic link auth + powiadomienia)

## Wymagania zewnętrzne

- Konto Tavily (API key) — https://tavily.com
- Konto OpenAI (API key) — https://platform.openai.com
- Konto Google Cloud (OAuth 2.0 client ID) — do logowania przez Google
- Serwis email (Resend API key lub konfiguracja SMTP) — do magic linków i powiadomień
- PostgreSQL 15+

## Zmienne środowiskowe

```env
DATABASE_URL=postgresql://user:password@localhost:5432/pulsefeed
SECRET_KEY=random-secret-key-for-jwt

TAVILY_API_KEY=tvly-xxxxx
OPENAI_API_KEY=sk-xxxxx
OPENAI_MODEL=gpt-4.1-nano

GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxxxx

EMAIL_PROVIDER=resend  # lub "smtp"
RESEND_API_KEY=re_xxxxx
# lub dla SMTP:
# SMTP_HOST=smtp.example.com
# SMTP_PORT=587
# SMTP_USER=user
# SMTP_PASSWORD=password
EMAIL_FROM=noreply@pulsefeed.app

APP_URL=https://app.pulsefeed.app
API_URL=https://api.pulsefeed.app
COOKIE_DOMAIN=.pulsefeed.app

# Opcjonalne
DEFAULT_CHECK_INTERVAL_DAYS=7
MAX_SEARCH_RESULTS_PER_TOPIC=5
```

## Struktura projektu

```
backend/
├── app/
│   ├── main.py                  # FastAPI app, CORS, startup/shutdown
│   ├── config.py                # Pydantic settings z env vars
│   ├── database.py              # SQLAlchemy engine, session
│   │
│   ├── models/                  # SQLAlchemy models
│   │   ├── user.py
│   │   ├── topic.py
│   │   ├── fact.py
│   │   ├── check_result.py
│   │   └── notification.py
│   │
│   ├── schemas/                 # Pydantic schemas (request/response)
│   │   ├── user.py
│   │   ├── topic.py
│   │   ├── auth.py
│   │   └── notification.py
│   │
│   ├── api/                     # Route handlers
│   │   ├── auth.py              # Google OAuth, magic link, session
│   │   ├── topics.py            # CRUD tematów, dodawanie z URL
│   │   └── users.py             # Ustawienia użytkownika
│   │
│   ├── services/                # Logika biznesowa
│   │   ├── article_analyzer.py  # Pobieranie URL, ekstrakcja tematu przez AI
│   │   ├── topic_checker.py     # Sprawdzanie nowych info (Tavily + AI)
│   │   ├── fact_comparer.py     # Porównywanie nowych faktów z zapisanymi
│   │   ├── notification.py      # Wysyłka emaili
│   │   └── auth.py              # Logika auth (tokeny, magic link, OAuth)
│   │
│   ├── jobs/                    # Background tasks
│   │   └── scheduler.py         # Konfiguracja schedulera, job sprawdzania tematów
│   │
│   └── prompts/                 # Prompty AI (jako pliki tekstowe)
│       ├── extract_topic.txt    # Ekstrakcja tematu z artykułu
│       ├── generate_keywords.txt # Generowanie słów kluczowych do searcha
│       ├── analyze_results.txt  # Analiza wyników searcha
│       └── compare_facts.txt    # Porównanie nowych vs znanych faktów
│
├── alembic/                     # Migracje
│   └── versions/
├── alembic.ini
├── requirements.txt
├── Dockerfile
├── Procfile                     # Dla Dokku (web + worker)
└── .env.example
```

## Model danych

### User
- `id` (UUID, PK)
- `email` (unique)
- `google_id` (nullable, unique) — dla Google OAuth
- `language` (string, default "en") — język UI i powiadomień
- `default_check_interval_days` (int, default 7) — domyślna częstotliwość sprawdzania nowych tematów
- `credits_remaining` (int) — liczba pozostałych kredytów
- `created_at`, `updated_at`

### Topic
- `id` (UUID, PK)
- `user_id` (FK → User)
- `source_url` (string) — oryginalny URL artykułu
- `title` (string) — tytuł tematu zidentyfikowany przez AI (np. "Ekranizacja powieści Starter Villain Johna Scalziego")
- `description` (text) — krótki opis kontekstu tematu
- `search_keywords` (JSON array of strings) — słowa kluczowe do wyszukiwania aktualizacji
- `check_interval_days` (int) — częstotliwość sprawdzania (nadpisuje domyślną usera)
- `next_check_at` (datetime) — kiedy następne sprawdzenie
- `last_checked_at` (datetime, nullable)
- `has_update` (boolean, default false) — czy są nowe info od ostatniej wizyty usera
- `status` (enum: active, paused, archived)
- `source_language` (string) — język oryginalnego artykułu
- `created_at`, `updated_at`

### Fact
- `id` (UUID, PK)
- `topic_id` (FK → Topic)
- `content` (text) — treść faktu wyekstrahowana przez AI
- `source_url` (string) — skąd pochodzi fakt
- `source_title` (string) — tytuł źródła
- `discovered_at` (datetime) — kiedy fakt został odkryty
- `is_initial` (boolean) — czy pochodzi z oryginalnego artykułu (true) czy z późniejszego sprawdzenia (false)

### CheckResult
- `id` (UUID, PK)
- `topic_id` (FK → Topic)
- `checked_at` (datetime)
- `search_queries_used` (JSON) — jakie zapytania zostały użyte
- `sources_found` (int) — ile źródeł znaleziono
- `new_facts_count` (int) — ile nowych faktów odkryto
- `credits_used` (int)
- `raw_results` (JSON, nullable) — surowe wyniki do debugowania

### Notification
- `id` (UUID, PK)
- `user_id` (FK → User)
- `topic_id` (FK → Topic)
- `type` (enum: new_facts, topic_added, credits_low)
- `sent_at` (datetime)
- `read_at` (datetime, nullable)

## API Endpoints

### Auth
```
POST   /auth/google          # Google OAuth callback → zwraca JWT
POST   /auth/magic-link      # Wysyła magic link na email
POST   /auth/verify           # Weryfikuje magic link token → zwraca JWT
GET    /auth/me               # Aktualny user
POST   /auth/logout           # Unieważnienie sesji
```

### Topics
```
POST   /topics                # Dodaj temat z URL-a
GET    /topics                # Lista tematów usera (z flagą has_update)
GET    /topics/:id            # Szczegóły tematu (z faktami i historią sprawdzeń)
PATCH  /topics/:id            # Zmiana ustawień tematu (częstotliwość, status)
DELETE /topics/:id            # Usunięcie tematu
POST   /topics/:id/check     # Wymuś sprawdzenie teraz (kosztuje kredyt)
POST   /topics/:id/mark-read # Oznacz aktualizacje jako przeczytane
```

### User
```
GET    /users/settings        # Pobierz ustawienia
PATCH  /users/settings        # Zmień ustawienia (język, domyślna częstotliwość)
GET    /users/credits         # Stan kredytów i historia użycia
```

### Notifications
```
GET    /notifications         # Lista powiadomień usera
POST   /notifications/mark-read  # Oznacz jako przeczytane
```

## Kluczowe przepływy (flows)

### 1. Dodawanie tematu z URL-a

```
User wysyła POST /topics z { "url": "https://..." }
  → Backend pobiera treść artykułu (Tavily Extract lub requests + BeautifulSoup)
  → Treść wysyłana do OpenAI z promptem extract_topic
  → AI zwraca:
     - 1-3 propozycje tematu (tytuł + opis), posortowane od najtrafniejszej
     - Propozycje muszą być merytorycznie różne, nie stylistycznie
     - Np. artykuł o wypadku na Mickiewicza może dać:
       1. "Wypadek na ul. Mickiewicza 2 lutego 2025 — losy poszkodowanych"
       2. "Śledztwo ws. wypadku na ul. Mickiewicza 2 lutego 2025"
     - Ale NIE: ten sam temat sformułowany inaczej
  → Jeśli AI ma jedną wyraźną interpretację → zwraca jedną propozycję
  → Response do usera: lista propozycji do wyboru
  → User wybiera → POST /topics/confirm z wybranym tematem
  → AI generuje słowa kluczowe (prompt generate_keywords) w języku źródła + angielskim
  → AI ekstrahuję fakty z artykułu (zapisane jako Fact z is_initial=true)
  → Topic zapisany, next_check_at ustawione
```

### 2. Sprawdzanie tematu (background job)

```
Scheduler co godzinę sprawdza: SELECT * FROM topics WHERE next_check_at <= NOW() AND status = 'active'
  → Dla każdego tematu:
     1. Wyszukaj w Tavily używając search_keywords (basic search, max 5 wyników)
     2. Wyekstrahuj treść znalezionych artykułów (Tavily Extract)
     3. Wyślij do AI (prompt analyze_results):
        - Kontekst: tytuł tematu, opis, lista znanych faktów
        - Nowa treść: wyniki searcha
        - Pytanie: "Czy w tych wynikach są NOWE FAKTY, których nie ma na liście znanych faktów?"
     4. AI musi odfiltrować:
        - Duplikaty (ten sam news w innym serwisie)
        - Przepisane artykuły (parafrazowane, ale bez nowych informacji)
        - Nieistotne wyniki (inne tematy, które pasują do słów kluczowych)
     5. Jeśli są nowe fakty:
        - Zapisz je jako Fact (is_initial=false)
        - Ustaw topic.has_update = true
        - Wyślij powiadomienie email do usera
     6. Zapisz CheckResult
     7. Odejmij kredyt z konta usera
     8. Ustaw next_check_at = NOW() + check_interval_days
```

### 3. Filtracja fałszywych pozytywów (kluczowy element jakości)

AI w kroku analizy wyników musi działać na poziomie faktów, nie tekstu. Prompt compare_facts powinien:

- Wyekstrahować konkretne fakty z nowych artykułów (daty, liczby, nazwiska, decyzje, wydarzenia)
- Porównać każdy fakt z listą znanych faktów
- Nowy fakt to TYLKO taki, który wnosi informację nieznaną z dotychczasowych faktów
- Przykłady tego co NIE jest nowym faktem:
  - Ten sam fakt opisany innymi słowami
  - Ogólne podsumowanie sytuacji bez nowych szczegółów
  - Opiniotwórcze artykuły komentujące znane fakty
  - Artykuły z innego serwisu opisujące to samo wydarzenie

## Deploy (Dokku)

Aplikacja działa jako dwa procesy (Procfile):

```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
worker: python -m app.jobs.scheduler
```

### Dockerfile

Obraz powinien zawierać Python 3.12, zależności z requirements.txt. Dokku automatycznie wykrywa Dockerfile.

### Konfiguracja Dokku

```bash
# Stworzenie aplikacji
dokku apps:create pulsefeed-api

# PostgreSQL
dokku postgres:create pulsefeed-db
dokku postgres:link pulsefeed-db pulsefeed-api

# Zmienne środowiskowe
dokku config:set pulsefeed-api SECRET_KEY=xxx TAVILY_API_KEY=xxx OPENAI_API_KEY=xxx ...

# Domena
dokku domains:set pulsefeed-api api.pulsefeed.app

# SSL
dokku letsencrypt:enable pulsefeed-api

# Skalowanie (web + worker)
dokku ps:scale pulsefeed-api web=1 worker=1
```

## Uruchomienie lokalne

```bash
# Klonowanie
git clone <repo-url>
cd backend

# Środowisko wirtualne
python -m venv venv
source venv/bin/activate

# Zależności
pip install -r requirements.txt

# Zmienne środowiskowe
cp .env.example .env
# Uzupełnij .env

# Baza danych
alembic upgrade head

# Uruchomienie API
uvicorn app.main:app --reload --port 8000

# Uruchomienie workera (osobny terminal)
python -m app.jobs.scheduler
```

## Wytyczne dla AI (Claude Code)

### Styl kodu
- Python 3.12+, type hints wszędzie
- Async endpoints w FastAPI
- Pydantic v2 dla schematów
- Komentarze w kodzie po angielsku
- Nazewnictwo zmiennych i funkcji po angielsku

### Bezpieczeństwo
- JWT w httpOnly cookies (nie w localStorage)
- CORS ograniczony do APP_URL
- Rate limiting na endpointach auth
- Walidacja wszystkich inputów przez Pydantic
- Nie loguj API keys ani danych osobowych

### Obsługa błędów
- Spójne response body dla błędów: `{ "detail": "message", "code": "ERROR_CODE" }`
- Obsługa timeout'ów Tavily i OpenAI (retry z backoff)
- Graceful handling gdy użytkownik nie ma kredytów

### Prompty AI
- Prompty trzymane w osobnych plikach .txt w katalogu app/prompts/
- Prompty w języku angielskim (AI lepiej działa po angielsku)
- Odpowiedzi AI w formacie JSON (structured output)
- Każdy prompt powinien mieć jasną instrukcję co do formatu odpowiedzi
