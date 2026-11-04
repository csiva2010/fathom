# Fathom · AI Finance Assistant

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
                                                  ├─ LangGraph workflow (workflow/)
                                                       load_context → router ─┬─ advice redirect / clarify
                                                                              └─ agents in parallel (Send)
                                                  │    → fallback → synthesizer → compliance
                                                  └─ Personal access tokens (Bearer) for MCP
Claude Desktop ──stdio──▶ MCP server (backend/src/mcp_server) ──REST, Bearer token──▶ same API
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
cd frontend && npm run test:coverage && npm run lint && npm run typecheck
```

CI (`.github/workflows/ci.yml`) runs all of these, enforces 90% coverage on both backend and
frontend, rebuilds the knowledge base, runs the offline evaluation sets, and checks that the
frontend's generated API types match the backend schema.

## Evaluation (golden sets)

Golden sets live in `backend/tests/eval/golden/`:

| Set | Cases | Measures |
| --- | --- | --- |
| `retrieval.yaml` | 52 questions + 4 off-topic | hit@1/3/5, MRR@5, context precision@5, abstention |
| `routing.yaml` | 42 messages | agent recall/precision per agent, advice redirects, clarifications, tickers, follow-ups |
| `compliance.yaml` | 20 drafts + 18 messages | precision/recall of the advice-language and advice-request detectors |
| `answers.yaml` | 15 full turns | agents, cited sources, charts, disclaimer, no advice; faithfulness (live) |

```bash
cd backend
.venv/bin/python -m scripts.run_evals                    # offline: no keys, deterministic (CI)
.venv/bin/python -m scripts.run_evals --live --pause 4   # real models + LLM faithfulness judge
.venv/bin/python -m scripts.run_evals --live --suite answers --case ans-01 ans-04
```

Offline runs the real knowledge base with keyword retrieval, rule routing, template answers
and mock market data; `tests/eval/test_offline_evals.py` fails CI if a metric drops below its
floor (`OFFLINE_FLOORS` in `tests/eval/harness.py`). Live runs use `backend/.env` and make
about 150 model calls. Reports (Markdown + JSON) are written to `backend/var/evals/`.

## "How I answered" trace

Every workflow node records its latency, model calls, tokens, models used (and whether a
fallback model answered) and tool calls. The trace streams to the chat as `trace` events,
is saved with each answer, and shows under it in a collapsible "How I answered" panel.

For the full run tree (every LangGraph node, prompt, model response and tool call), turn on
LangSmith in `backend/.env`: `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY=...`
(optional `LANGSMITH_PROJECT`, default `fathom`; EU accounts also set
`LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com`). The API exports these when it
starts, so restart it after changing them. Live evals trace to `<project>-evals`; tests and
offline evals never trace.

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

## Claude Desktop (MCP server)

`backend/src/mcp_server` is a small MCP server that Claude Desktop launches over stdio. It
calls this app's REST API with a personal access token, so Claude Desktop sees your
portfolios and goals and gets the same numbers as the web app. Provider and LLM keys never
leave the backend.

| Tool | Backed by |
|---|---|
| `get_quote(symbols)` | `GET /market/quotes` |
| `get_market_overview()` | `GET /market/overview`, `/market/sectors`, `/market/movers` |
| `list_portfolios()` | `GET /portfolios` |
| `analyze_portfolio(portfolio_id? \| holdings?, benchmark_range)` | `GET /portfolios/{id}/analysis` or `POST /portfolios/analyze`; with neither, your latest saved portfolio |
| `project_goal(target_amount, years \| target_date, ...)` | `POST /goals/project`; risk profile defaults to your saved one |
| `search_knowledge_base(query, category?)` | `GET /kb/search` (the chat's hybrid retriever) |
| `explain_term(term)` | `GET /kb/glossary/{term}` |

Every tool is read-only, its description carries the educational disclaimer, and market
results include `freshness`.

Setup:

1. Start the API (and the web app) as usual.
2. Open **Profile → Claude Desktop access** and create a token. It is shown once; only its
   hash is stored. Tokens can be revoked there, and a token can't create or revoke tokens.
3. In Claude Desktop, open **Settings → Developer → Edit Config** and add the block the
   Profile page shows, with your checkout's absolute path:

   ```json
   {
     "mcpServers": {
       "finance-assistant": {
         "command": "/abs/path/to/fathom/backend/.venv/bin/python",
         "args": ["-m", "src.mcp_server"],
         "env": {
           "PYTHONPATH": "/abs/path/to/fathom/backend",
           "FINANCE_API_URL": "http://localhost:5173/api/v1",
           "FINANCE_API_TOKEN": "fa_pat_..."
         }
       }
     }
   }
   ```

   `FINANCE_API_URL` is the web app's origin plus `/api/v1` (use your `WEB_PORT`, or the
   deployed domain). Pointing at `API_PORT` directly also works.
4. Restart Claude Desktop. The tools appear under the connectors (tools) menu; try "Analyze
   my portfolio" or "What does SIPC protect?". Server logs are in Claude Desktop's MCP log
   files (`~/Library/Logs/Claude/mcp-server-finance-assistant.log` on macOS).

The token authenticates as you, so the backend must be reachable from the machine running
Claude Desktop. If the token is rejected, the tools say so; create a new one and update the
config.

## Deployment

To run Fathom on a Google Cloud or AWS VM (nginx + systemd, single origin, data on the VM's
disk), follow [docs/deployment.md](docs/deployment.md). It also covers HTTPS with Google
sign-in and what to do in restricted AWS accounts.

## Troubleshooting

- **Port already in use**: change `WEB_PORT` / `API_PORT` in both `backend/.env` and
  `frontend/.env`, restart both servers, and register the new Google redirect URI.
- **`/api` calls return `{"detail": "Not Found"}`**: the Vite proxy is reaching another app on
  `API_PORT`; make sure the two `.env` files agree and the API actually started.
- **401 on every call after sign-in**: the session cookie must be same-origin; open the app via
  the Vite URL, not the API port.
- **Claude Desktop shows no finance tools**: check the MCP log above. "Set FINANCE_API_URL
  and FINANCE_API_TOKEN" means the `env` block is missing; `No module named src` means
  `PYTHONPATH` doesn't point at `backend/`.
- **Market cards say "Sample data"**: market keys are missing or the provider is down; check
  the Profile tab's System status or run `scripts.check_providers`.

_For education only. Not investment, tax or legal advice._
