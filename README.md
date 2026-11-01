# AI Finance Assistant

An educational, multi-agent finance assistant. It explains concepts in plain language,
analyzes a portfolio you enter, shows live market context, and helps plan goals at your
risk level. It never gives personalized investment advice.

> **Status: day 3 of the one-week build plan.** Sign-in, configuration, database, CI, the
> market-data layer, the knowledge base (110 articles, 259 glossary terms) with hybrid
> retrieval, and the LangGraph workflow with the Finance Q&A and Market Analysis agents are in
> place. The chat endpoint (SSE) and the remaining four agents come next. See `docs/` for the
> PRD and technical design.

## Architecture (today)

```
React SPA (frontend/) ──REST, session cookie──▶ FastAPI (backend/src/web_app)
                                                  ├─ Google OAuth + signed HttpOnly session
                                                  ├─ MarketDataService (core/services/market)
                                                  │    └─ ProviderChain: cache → Alpaca / Alpha Vantage → stale cache → mock
                                                  │         └─ rate limit · retry/backoff · circuit breaker
                                                  ├─ SQLite via SQLAlchemy + Alembic (Postgres-ready)
                                                  ├─ RAG (rag/): BM25 + ChromaDB vectors (Gemini, OpenAI fallback)
                                                  │    └─ reciprocal rank fusion → cross-encoder rerank → threshold
                                                  └─ LangGraph workflow (workflow/)
                                                       load_context → router ─┬─ advice redirect / clarify
                                                                              └─ agents in parallel (Send)
                                                       → fallback → synthesizer → compliance
```

LLM calls go through one gateway (`core/llm`) that tries Gemini Flash, then Claude. With no
LLM key set, the router falls back to keyword rules and agents answer from retrieved sources
and service data, so the app still works.

## Prerequisites

- Python 3.11+
- Node 20+

## Setup

```bash
# Backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env              # then fill in keys (see below)
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.seed_db
.venv/bin/python -m scripts.ingest_kb
.venv/bin/python -m scripts.run_api     # serves on API_PORT (default 8000)

# Frontend (second terminal)
cd frontend
npm install
cp .env.example .env
npm run dev                        # serves on WEB_PORT (default 5173)
```

Interactive API docs: `http://localhost:<API_PORT>/api/v1/docs`

### Ports

Both ports are set in the `.env` files, and the two files must agree:

| Variable | `backend/.env` | `frontend/.env` | Default |
| --- | --- | --- | --- |
| `WEB_PORT` | derives the web app URL, CORS origin and Google redirect URI | Vite dev server port | 5173 |
| `API_PORT` | port for `scripts.run_api` | where Vite proxies `/api` | 8000 |

Vite uses `strictPort`, so it stops with an error if `WEB_PORT` is taken instead of silently
moving to another port (which would break Google sign-in).

### Keys (`backend/.env`)

| Variable | Used for |
| --- | --- |
| `SESSION_SECRET` | Signs session cookies. Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google sign-in |
| `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY` | Quotes, price history, news |
| `ALPHA_VANTAGE_API_KEY` | Index quotes, sector and fund data |
| `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | LLMs and embeddings (from day 2) |

Without market keys the app runs on clearly labelled sample data.

### Sign-in mode (`AUTH__MODE` in `backend/.env`)

| Value | Landing page shows | Accounts | Production |
| --- | --- | --- | --- |
| `google` (default) | Sign in with Google | One per Google account | Yes |
| `guest` | Continue as guest (Google sign-in disabled) | A new, isolated account per visitor; it lasts as long as the session cookie (12 h, renewed while in use) | Yes |
| `stub` | Sign in with Google (no real Google) | Everyone is one fixed dev user | Refused |

Use `guest` when Google OAuth isn't configured but people other than you will use the app
(for example graders). Signing out or clearing cookies abandons a guest's data.

### Google OAuth client

1. In Google Cloud Console → APIs & Services → Credentials, create an **OAuth client ID** of
   type *Web application*.
2. Authorized redirect URI: `http://localhost:<WEB_PORT>/api/v1/auth/google/callback` for local
   dev (the Vite dev server proxies `/api` to the backend, so the cookie is same-origin). On the
   central server, use `https://<your-domain>/api/v1/auth/google/callback` and set
   `AUTH__GOOGLE_REDIRECT_URI`, `APP__FRONTEND_URL`, `APP__CORS_ORIGINS`,
   `AUTH__COOKIE_SECURE=true` and `APP__ENV=production`.
3. Put the client ID and secret in `backend/.env` and set `AUTH__MODE=google`.

## Day-1 gate check

```bash
cd backend && .venv/bin/python -m scripts.check_providers
```

This calls Alpha Vantage for each configured index (S&P 500, Nasdaq, Dow) and Alpaca for the
ETF proxies (SPY, QQQ, DIA), bypassing cache and mock data. If Alpha Vantage doesn't cover an
index symbol, the app automatically falls back to the ETF proxy and labels it as such. Index
symbols are set in `backend/config.yaml` under `market.indices`.

## Tests and checks

```bash
cd backend && .venv/bin/pytest --cov && .venv/bin/ruff check src scripts tests && .venv/bin/mypy src scripts
cd frontend && npm test && npm run lint && npm run typecheck
```

CI (`.github/workflows/ci.yml`) runs all of these, enforces 90% backend coverage, rebuilds the
knowledge base, and checks that the frontend's generated API types match the backend schema.

## Knowledge base

Articles live in `backend/data/kb/<category>/<id>.md` with YAML front matter (`id`, `title`,
`category`, `level`, `source_url`, `source_name`, `last_reviewed`). The glossary is
`backend/data/kb/glossary.yaml`. Ingestion fails on any missing or invalid field; use
`--lenient` to skip bad files while drafting. Content is written in our own words from
public sources (Investor.gov, FINRA, IRS, CFPB, Bogleheads).

`scripts.ingest_kb` rebuilds the BM25 index and one ChromaDB collection per embedding model
that has an API key (`GEMINI_API_KEY`, `OPENAI_API_KEY`); `--keyword-only` skips embeddings.
If the index is missing at startup, the API builds the keyword index itself.

The self-hosted cross-encoder reranker is optional because it needs PyTorch:

```bash
.venv/bin/pip install -r requirements-reranker.txt   # weights download on first use
```

Without it, retrieval logs a warning and uses a lexical reranker (`kb.reranker` in
`config.yaml`).

## Troubleshooting

- **Port already in use**: change `WEB_PORT` / `API_PORT` in both `backend/.env` and
  `frontend/.env`, restart both servers, and register the new Google redirect URI.
- **`/api` calls return `{"detail": "Not Found"}`**: the Vite proxy is reaching another app on
  `API_PORT`; make sure the two `.env` files agree and the API actually started.
- **401 on every call after sign-in**: the session cookie must be same-origin; open the app via
  the Vite URL, not the API port.
- **Market cards say "Sample data"**: market keys are missing or the provider is down; check
  the Profile tab's System status or run `scripts.check_providers`.

_For education only. Not investment, tax or legal advice._
