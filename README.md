# Aura — Lead Generation & CRM Data Collection Platform

A production-ready, conversion-focused lead capture website: a responsive React landing
page with a multi-step lead form, a secure FastAPI backend with PostgreSQL storage, a
pluggable CRM integration layer with retries and audit logging, and a protected admin
dashboard with search, filters, CSV export and one-click CRM re-synchronization.

---

## Architecture

```
┌────────────────────────────┐        ┌──────────────────────────────────────┐
│  Frontend (React + TS)     │        │  Backend (FastAPI + SQLAlchemy)      │
│  ─────────────────────     │        │  ──────────────────────────────      │
│  Landing page              │  POST  │  POST /api/leads                     │
│  Multi-step lead form      │ ─────► │   • rate limit + honeypot            │
│   (config-driven fields)   │        │   • validate + sanitize (Pydantic)   │
│  Review & submit           │  201   │   • duplicate & idempotency check    │
│                            │ ◄───── │   • save lead (status: pending)      │
│  Admin dashboard (/admin)  │  JWT   │   • background CRM sync + retries    │
│   stats / filters / export │ ─────► │  /api/auth/login   /api/admin/*      │
└────────────────────────────┘        │      │                               │
                                      │      ▼                               │
                                      │  PostgreSQL ──► CRM integration      │
                                      │  leads/sync_logs   layer (pluggable: │
                                      │  admin_users    mock | generic_rest) │
                                      └──────────────────────────────────────┘
```

**Data flow for a submission:** validate → sanitize → duplicate check → store locally
(`crm_sync_status = pending`) → respond 201 immediately → background task pushes to CRM
with exponential-backoff retries → every attempt is written to `sync_logs` → status
becomes `synced` (with the CRM's lead id) or `failed` (retryable manually or in bulk).
**A lead is never lost because the CRM is down.**

## Tech Stack

| Layer     | Technology |
|-----------|------------|
| Frontend  | React 18, TypeScript, Tailwind CSS, Vite, React Router, Vitest |
| Backend   | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic |
| Database  | PostgreSQL (production) / SQLite (zero-config dev & tests) |
| Auth      | JWT (python-jose), PBKDF2-HMAC-SHA256 password hashing |
| CRM       | Pluggable provider layer: `mock`, `generic_rest`, `none` |
| Deploy    | Docker, docker-compose, nginx |

## Project Structure

```
Aura-web/
├── backend/
│   ├── app/
│   │   ├── main.py             # app factory, CORS, lifespan (migrate + seed)
│   │   ├── config.py           # env-driven settings (pydantic-settings)
│   │   ├── database.py         # engine/session factories, Base
│   │   ├── models.py           # Lead, AdminUser, SyncLog
│   │   ├── schemas.py          # validation + sanitization boundaries
│   │   ├── security.py         # PBKDF2, JWT, sanitizers
│   │   ├── rate_limit.py       # sliding-window limiter
│   │   ├── deps.py / crud.py   # DI + DB access
│   │   ├── crm/                # base (field mapping), mock, generic_rest, factory
│   │   ├── services/sync.py    # sync orchestration, retries, audit
│   │   └── routers/            # leads (public), auth, admin
│   ├── alembic/                # migrations (0001_initial)
│   ├── tests/                  # 50 tests: validation, API, admin, CRM sync
│   └── requirements.txt / .env.example / Dockerfile
├── frontend/
│   ├── src/
│   │   ├── config/formConfig.ts   # ← add/remove/reorder form fields here
│   │   ├── form/                  # MultiStepForm, FieldRenderer, ProgressSteps, ReviewStep
│   │   ├── sections/ pages/       # landing sections, admin pages
│   │   ├── admin/                 # dashboard components
│   │   └── lib/                   # api client, validation, types (+ tests)
│   └── Dockerfile / nginx.conf
└── docker-compose.yml
```

## Quick Start (local development)

### 1. Backend

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate     # Windows
# source .venv/bin/activate                        # macOS/Linux
pip install -r requirements.txt
copy .env.example .env                              # adjust if needed
uvicorn app.main:app --reload
```

- API runs at http://localhost:8000 — interactive docs at http://localhost:8000/api/docs
- SQLite is used by default (no DB server needed). Tables auto-create on startup and a
  default admin is seeded: **admin@example.com / ChangeMe!123** (change in `.env`).
- For PostgreSQL: set `DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/dbname`
  and `DB_AUTO_CREATE=false`, then run `alembic upgrade head`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 (proxies /api → :8000)
```

- Landing page: http://localhost:5173
- Admin dashboard: http://localhost:5173/admin (sign in with the seeded admin)

### 3. Run the test suites

```bash
cd backend && python -m pytest          # 48 tests
cd frontend && npx vitest run           # 12 tests
cd frontend && npm run build            # type-check + production build
```

## CRM Integration

The website is aligned to the user's existing **AURA Self-Evolving CRM** — workspace
`Analytical_E_Commerce_CRM`, entity **Machine Identifier** (see
`docs/CRM_MAPPING_WORKSHEET.md`). The form mirrors the entity's 6 dynamic fields
(Customer Name, Customer Segment, Total Revenue, Purchase Frequency, Customer Value,
CRM Status) and submissions are created in the CRM with pipeline stage **New** and
source **Website**.

The integration layer is **modular** — set the provider via environment variables:

| Variable | Purpose |
|----------|---------|
| `CRM_PROVIDER` | `aura_crm` (your AURA CRM), `mock` (default), `generic_rest`, or `none` |
| `AURA_CRM_API_URL` | AURA create-record endpoint (from the captured request — see below) |
| `AURA_CRM_API_KEY` | Credential — sent via `AURA_CRM_AUTH_HEADER`/`AURA_CRM_AUTH_SCHEME` (e.g. `Authorization: Bearer …` or `x-api-key: …`) — **never** exposed to the frontend |
| `AURA_CRM_EXTRA_PAYLOAD` | Optional JSON merged into every request (e.g. `{"workspace": "…", "entity": "machine_identifier"}`) |
| `CRM_RESPONSE_ID_PATH` | Dotted path to the created record id in the JSON response (e.g. `data.id`) |
| `CRM_FIELD_MAPPING` | Optional JSON object overriding the default field mapping |
| `CRM_MAX_ATTEMPTS` / `CRM_RETRY_BACKOFF_SECONDS` | Retry policy (exponential backoff) |

Default mapping (mirrors the AURA entity labels; confirm exact payload keys from the
captured request, then adjust via `CRM_FIELD_MAPPING`):

```json
{"Customer Name": "customer_name", "Customer Segment": "customer_segment",
 "Total Revenue": "total_revenue", "Purchase Frequency": "purchase_frequency",
 "Customer Value": "customer_value", "CRM Status": "crm_status", "Source": "source",
 "External Reference": "reference"}
```

**Building the AURA endpoint?** Follow `docs/AURA_API_CONTRACT.md` — an exact
request/response contract (plus a FastAPI reference implementation) that plugs into
this backend with zero code changes, including idempotent handling of retried
submissions via `External Reference`.

**Connecting the real AURA instance:** the endpoint and auth are intentionally not
hardcoded. Capture the create-record request once (F12 → Network → create a record →
Copy as cURL — see `docs/CRM_MAPPING_WORKSHEET.md` section F), paste the values into
`backend/.env` (`CRM_PROVIDER=aura_crm`, `AURA_CRM_API_URL`, `AURA_CRM_API_KEY`, …),
and restart — submissions will then appear as new records in the CRM.

To support a specific CRM (HubSpot, Zoho, Salesforce…), subclass `CRMClient` in
`backend/app/crm/`, register it in `factory.py` — the retry, audit-log and admin
machinery work unchanged.

**Recovery guarantees:** if the CRM is unreachable, the lead stays in the database with
status `failed` (with `sync_logs` audit entries). Admins can retry a single lead or all
pending/failed leads from the dashboard or via `POST /api/admin/sync/retry-pending`
(also suitable for a cron/worker).

> **Note:** the shipped `mock` provider simulates the CRM for development and tests.
> Real synchronization requires configuring `CRM_PROVIDER=generic_rest` with your CRM's
> endpoint and credentials — no external endpoints are fabricated.

## API Reference (summary)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/api/leads` | public (rate-limited) | Submit a lead; validates, dedupes, queues CRM sync |
| GET | `/api/health` | public | Health check |
| POST | `/api/auth/login` | public (rate-limited) | Admin login → JWT |
| GET | `/api/auth/me` | Bearer | Current admin |
| GET | `/api/admin/stats` | Bearer | Totals: leads, synced, pending, failed, spam, today |
| GET | `/api/admin/leads` | Bearer | List with `q`, `status`, `sync_status`, `date_from`, `date_to`, `page`, `page_size` |
| GET | `/api/admin/leads/{id}` | Bearer | Lead detail incl. sync log |
| GET | `/api/admin/leads/export.csv` | Bearer | CSV export (same filters) |
| POST | `/api/admin/leads/{id}/retry-sync` | Bearer (admin role) | Retry CRM sync for one lead |
| POST | `/api/admin/sync/retry-pending` | Bearer (admin role) | Retry all pending/failed leads |

Full interactive documentation: `/api/docs` (Swagger UI) on a running backend.

## Security & Data Protection

- **Server-side validation & sanitization** (Pydantic): email/E.164 phone/URL format
  checks, length limits, HTML tag stripping, control-character removal.
- **Duplicate & idempotency protection:** same email within a configurable window →
  `409 DUPLICATE_LEAD`; client-generated `submission_id` makes retries safe.
- **Spam protection:** hidden honeypot field (bots get a plausible 201 but are quarantined
  as `spam` and never synced) + per-IP sliding-window rate limits on submit and login.
- **AuthN/Z:** JWT bearer tokens, PBKDF2-hashed passwords, role-based access
  (`admin` vs read-only `viewer`), generic login errors, expiring sessions.
- **Secrets:** all credentials/keys come from environment variables; nothing sensitive
  in frontend code or logs (client IPs stored only as SHA-256 hashes).
- **Consent management:** privacy/contact consent enforced server-side; marketing
  consent stored separately.
- **SQL-injection/XSS:** SQLAlchemy parameterization throughout; React escaping +
  server-side tag stripping.
- **HTTPS:** terminate TLS at your reverse proxy/ingress; nginx ships security headers
  and forwards `X-Forwarded-*`. Honeypot/rate-limit cover bot basics; wire reCAPTCHA or
  Turnstile into `POST /api/leads` if you need stronger verification.

## Deployment (Docker)

```bash
# from the repo root — set real secrets first
docker compose up --build
```

- Frontend: http://localhost:8080 (nginx serves the SPA, proxies `/api` to the backend)
- Backend: http://localhost:8000 · PostgreSQL 16 with a persistent volume
- The backend container runs `alembic upgrade head` on start, then launches uvicorn.
- Frontend and backend images are independent and can be deployed separately.

## Customizing the Lead Form

Fields are **fully config-driven** in `frontend/src/config/formConfig.ts`:
add/remove/reorder fields, change options, mark fields required/optional, add
`conditional: { field, equals }` rules — the UI, validation and review screen update
automatically. For persisted new fields, add the matching column to
`backend/app/models.py`, the schema in `schemas.py`, and generate a migration with
`alembic revision --autogenerate -m "add field"`.

## Environment Variables

Backend — see `backend/.env.example` (core, auth, rate limits, CRM). Frontend —
`frontend/.env.example` (`VITE_API_BASE_URL`, usually left empty).

## Limitations & Notes

- The in-memory rate limiter suits single-process deployments; use Redis for multi-instance.
- CRM sync runs as an in-process background task; for very high volume move
  `sync_lead_by_id` to a queue worker (Celery/RQ) — the service function is reusable.
- The `mock` CRM provider is for development/demo; configure `generic_rest` (or a custom
  provider subclass) with real credentials for production synchronization.
