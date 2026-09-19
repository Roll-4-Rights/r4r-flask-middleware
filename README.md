# Roll4Rights Donate API

Flask middleware for the **donate site** — the API layer between `donate.roll4rights.duckdns.org` and backend services (NocoDB, PostgreSQL). Frontends never talk to NocoDB directly; this service holds the API token, enforces auth, and proxies data access.

Auction functionality (bidding, bidder login, winner claims) lives in a **separate API app** (`r4r-auction-api` or similar).

## What it does

- **Donator portal** — registration, login, donations, messages, profile, media uploads
- **Public content** — campaign info, announcements, FAQs, calendar, banner messages
- **Admin operations** — table writes and moderation via `X-API-Key`
- **Donation sync** — pushes accepted donations to NocoDB auction tables (consumed by the auction API)

```
┌─────────────────┐     ┌─────────────────┐
│  donate.*       │     │  auction.*      │
│  (frontend)     │     │  (frontend)     │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│  Donate API     │     │  Auction API    │
│  (this repo)    │     │  (separate app) │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └──────────┬────────────┘
                    ▼
         ┌──────────────────────┐
         │  NocoDB  +  Postgres │
         └──────────────────────┘
```

PostgreSQL stores donator accounts, invite codes, and forum messages. NocoDB stores campaign content, donations, donator profiles, and public site content. The auction API owns bidder accounts, bids, and winner-claim flows in its own Postgres tables.

## Project structure

```
├── app.py                  # Dev server entry point (remote containers expect this file)
├── wsgi.py                 # Optional WSGI alias
├── Procfile                # gunicorn app:app
├── db.py                   # PostgreSQL connection pool and queries
├── app/
│   ├── __init__.py         # Application factory (create_app)
│   ├── config.py           # Environment variables and NocoDB table IDs
│   ├── extensions.py       # Flask-Login
│   ├── models.py           # Donator user class
│   ├── decorators.py       # CSRF, API key, donator auth
│   ├── services/           # NocoDB, email, media helpers
│   └── blueprints/         # Route modules grouped by domain
├── sync_accepted_donations.py
└── scripts/                # One-off NocoDB setup and migration utilities
```

## Requirements

- Python 3.10+
- PostgreSQL
- NocoDB instance with the donator and site bases configured
- Write access to auction-item tables in NocoDB (for `sync_accepted_donations.py` only)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy environment variables into a `.env` file (see below). On first boot the app creates its PostgreSQL tables automatically (`donators`, `invite_codes`, and the lot number sequence).

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | Yes | Flask session signing key |
| `FLASK_ENV` | No | `development` or `production` (default: `production`) |
| `NOCODB_URL` | Yes | NocoDB base URL |
| `NOCODB_TOKEN` | Yes | NocoDB API token (never exposed to frontends) |
| `NOCODB_DONATOR_BASE_ID` | Yes | NocoDB base ID for donator data |
| `NOCODB_SITE_BASE_ID` | Yes | NocoDB base ID for site content |
| `POSTGRES_HOST` | Yes | PostgreSQL host |
| `POSTGRES_PORT` | No | Default `5432` |
| `POSTGRES_DB` | Yes | Database name |
| `POSTGRES_USER` | Yes | Database user |
| `POSTGRES_PASSWORD` | Yes | Database password |
| `MIDDLEWARE_API_KEY` | Yes | Protects admin write endpoints (`X-API-Key` header) |
| `ALLOWED_ORIGINS` | No | Comma-separated CORS origins (default: donate + auction prod URLs) |
| `REGISTRATION_PASSCODE` | No | Shared passcode for donator registration without an invite |
| `DONATE_APP_URL` | No | Donate frontend base URL for invite links |
| `SESSION_COOKIE_DOMAIN` | No | Session cookie domain (default: `.roll4rights.duckdns.org`) |
| `SESSION_LIFETIME_DAYS` | No | Remember-me session lifetime (default: `14`) |
| `UPLOAD_STORAGE_PATH` | No | Directory for profile picture uploads |
| `MAX_UPLOAD_BYTES` | No | Per-file upload limit (default: 10 MB) |
| `RATELIMIT_STORAGE_URI` | No | Flask-Limiter backend (default: `memory://`; use Redis in multi-worker prod) |

**NocoDB table IDs** (all required — no defaults in code):

| Variable | Table |
|---|---|
| `DONATIONS_TABLE_ID` | Donations and Tracking |
| `DONATOR_PROFILES_TABLE_ID` | Donator Profiles |
| `PUBLIC_CALENDAR_TABLE_ID` | Public Calendar |
| `TEAM_CALENDAR_TABLE_ID` | Team Calendar |
| `ANNOUNCEMENTS_TABLE_ID` | Announcements |
| `DONATOR_FAQS_TABLE_ID` | Donator FAQs |
| `DONATOR_MESSAGES_TABLE_ID` | Donator Messages |
| `AUCTION_ITEMS_TABLE_ID` | Auction Items |
| `BIDS_TABLE_ID` | Bids |
| `WINNERS_TABLE_ID` | Winners |
| `BANNER_MESSAGES_TABLE_ID` | Banner Messages |
| `SITE_CONTENT_TABLE_ID` | Site Content |
| `CAMPAIGN_TABLE_ID` | Campaign Settings |

Use `scripts/get_table_ids.py` to look up IDs from your NocoDB instance.

## Running

**Local development:**

```bash
FLASK_ENV=development python app.py
```

**Production (Gunicorn):**

```bash
gunicorn --bind 0.0.0.0:5000 app:app
```

The `Procfile` uses the same `app:app` target. Root `app.py` is a thin wrapper; `gunicorn` loads the `app` package from `app/__init__.py`.

**Health check:** `GET /api/health`

**API index:** `GET /` returns a minimal service status payload.

## Authentication

Donators authenticate with email and password. Sessions use Flask-Login with the prefix `donator:{id}` and a cookie scoped to `.roll4rights.duckdns.org` in production.

State-changing requests from the donate frontend must include a trusted `Origin` header (CSRF protection). Admin write operations use the `X-API-Key` header instead of session cookies.

## API overview

| Blueprint | Prefix / routes | Auth |
|---|---|---|
| `health` | `/api/health` | Public |
| `auth` | `/api/auth/*`, `/api/invites` | Mixed |
| `donations` | `/api/donations/*` | Donator |
| `messages` | `/api/messages` | Donator |
| `profile` | `/api/donator-profile`, `/api/auth/profile-picture`, `/api/profile-pictures/*` | Donator |
| `media` | `/api/upload`, `/api/media/*` | Donator |
| `calendar` | `/api/calendar` | Public |
| `campaign` | `/api/campaign`, `/api/campaign-progress`, `/api/campaign-info` | Public / API key |
| `content` | `/api/announcements`, `/api/donator-faqs`, `/api/site-content`, `/api/banner-messages` | Public / API key |
| `tables` | `/api/tables/<name>/*` | API key |
| `forum` | `/api/forum-messages` | API key |
| `admin` | `/api/admin/*` | API key |

NocoDB table IDs are defined in `app/config.py`. Update them there when tables are recreated (see `scripts/get_table_ids.py`).

### Auction API (separate app)

These endpoints are **not** served by this repo:

| Area | Routes |
|---|---|
| Auction items | `/api/auction/*` |
| Bidder auth | `/api/bidder/*` |
| Winner claims | `/api/winner-claim/*` |

Scheduled jobs for winner notification and claim expiry also run in the auction API.

## Scheduled tasks

Run via Coolify scheduled tasks or cron:

| Script | Purpose |
|---|---|
| `sync_accepted_donations.py` | Creates/updates NocoDB auction listings when a donation is marked Accepted |

## Scripts

The `scripts/` directory contains one-off utilities for NocoDB table setup and migration. These are run manually during initial setup or schema changes — not part of the running service.

## Security

- **Admin/table access** — all `/api/tables/*` routes require `X-API-Key` (no anonymous reads).
- **Field allowlists** — donation and profile writes only pass known NocoDB columns through.
- **Upload validation** — image type and size checks on `/api/upload` and winner-claim proof uploads.
- **Rate limits** — login, registration, invite verify, and bidder magic-link requests are throttled.
- **Production startup** — app refuses to boot without `SECRET_KEY`, `MIDDLEWARE_API_KEY`, and `NOCODB_TOKEN` when `FLASK_ENV` is not `development`.
- **Profile pictures** — require a donator session; served only for filenames stored in the database.

## Deployment / migration notes

When deploying this update to an existing environment, watch for:

1. **Production env vars** — deploy will **fail on startup** if `SECRET_KEY`, `MIDDLEWARE_API_KEY`, or `NOCODB_TOKEN` are missing and `FLASK_ENV=production`. Set these before redeploying.

2. **`pip install -r requirements.txt`** — adds `Flask-Limiter`. Required on the container.

3. **`GET /api/tables/*` breaking change** — any tool or frontend that read tables without `X-API-Key` will get `401`. Admin scripts must send the API key header on reads too.

4. **Profile picture URLs** — `<img src="...">` tags must hit the API with the donator session cookie (same parent domain, e.g. `.roll4rights.duckdns.org`). If avatars are loaded from a different domain without cookies, switch to `fetch(..., { credentials: 'include' })` + blob URLs.

5. **Donation/profile field allowlists** — extra JSON fields sent by the frontend are now silently dropped. If you rely on columns not in the allowlists in `app/services/validation.py`, add them there.

6. **Upload restrictions** — `/api/upload` now rejects non-images and files over `MAX_UPLOAD_BYTES` (default 10 MB). Video uploads will fail unless you extend validation.

7. **Rate limiting** — aggressive login/testing from one IP may hit `429`. For multi-worker Gunicorn, set `RATELIMIT_STORAGE_URI` to Redis (e.g. `redis://localhost:6379`) so limits are shared across workers.

8. **`ALLOWED_ORIGINS`** — must include every frontend origin that sends credentialed requests. Staging URLs must be added explicitly.

9. **Invite links** — use `DONATE_APP_URL` if the donate site URL differs from the production default.

10. **Sessions** — existing sessions remain valid, but remember-me cookies now expire after `SESSION_LIFETIME_DAYS` (default 14).

No database schema migrations are required for these changes.

## Development notes

- Lint/format locally: `ruff check app db.py app.py wsgi.py` and `ruff format app db.py app.py wsgi.py` (Black-compatible formatter).
- Set `FLASK_ENV=development` for local HTTP cookies (`SameSite=Lax`, no secure flag).
- `test.py` is a quick PostgreSQL connectivity check.
- Profile pictures are stored on disk under `uploads/profile_pictures/` (or `UPLOAD_STORAGE_PATH`).
- The generic `/api/tables/<table_name>` routes only expose tables listed in `TABLE_IDS`.
