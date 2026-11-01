# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

AI Finance Assistant: an educational, multi-agent finance assistant (capstone project).
A React SPA talks to one FastAPI backend over REST and SSE. A LangGraph state graph will route
chat messages to six agents, which call a shared services layer. Specs are in `docs/`:
the PRD (requirement IDs such as AG-, OR-, MD-, AU-, KB-, UI-, NF-) and the Technical Design
(architecture, API surface, data model, one-week build plan). Cite requirement IDs in docstrings
when code implements one.

## Repository layout

```
backend/                 Python 3.11+, FastAPI. Run every command from this folder.
  src/                   Course-prescribed layout (NF-Q02); keep these folder names.
    agents/              BaseAgent (prefetch + allow-listed tool loop) + finance_qa, market_analysis
    workflow/            LangGraph: state, context, router, responses, agent_runner,
                         synthesizer, compliance, graph, factory
    core/
      config/            Settings: config.yaml + .env merged by pydantic-settings
      llm/               LLMGateway: ordered model fallback (Gemini -> Claude), structured output
      logging/           Structured JSON logs with request/user/thread context
      errors/            AppError hierarchy -> {error: {code, message, retryable}}
      domain/            Pydantic domain models shared across layers (market.py)
      services/market/   MarketDataService, ranges, symbol validation, factory
    data/
      db/                SQLAlchemy models, session, repositories
      migrations/        Alembic (versions/0001_initial_schema.py, 0002_add_users_is_guest.py)
      providers/         alpaca/, alpha_vantage/, mock/ + chain.py (fallback order)
      resilience/        Token bucket, retry/backoff, circuit breaker, ProviderGuard
      cache/             In-process TTL cache with stale reads and request coalescing
    rag/                 ingestion/, keyword/ (BM25), embeddings, vector_store (Chroma),
                         reranker, retriever (hybrid + RRF + threshold), glossary, knowledge_base
    web_app/             FastAPI app: routers/, auth/, middleware/, errors/, schemas/
    utils/               Small pure helpers
    mcp_server/          MCP tools over the REST API (day 5)
  data/kb/<category>/    KB articles (Markdown + YAML front matter) and glossary.yaml
  data/seed/             Sample portfolios, reference data, mock base prices
  scripts/               ingest_kb, seed_db, check_providers, export_openapi
  tests/                 unit/ (mirrors src/), integration/, fixtures/
frontend/                React 18 + TypeScript (strict) + Vite + Tailwind + TanStack Query
  src/app/               App, routes, query client
  src/api/               fetch client, endpoints/, generated/ (OpenAPI types), types.ts
  src/lib/               auth/ (AuthProvider, useAuth, RequireAuth), format/
  src/components/        layout/, feedback/ (loading/empty/error), badges/, ui/
  src/features/<tab>/    One folder per tab: page + components/ + hooks/
docs/                    PRD and technical design (.docx)
```

## Commands

Backend (from `backend/`, venv at `backend/.venv`):

```bash
.venv/bin/python -m scripts.run_api                             # API on API_PORT, docs at /api/v1/docs
.venv/bin/alembic upgrade head                                  # migrate DB
.venv/bin/python -m scripts.seed_db                             # load 3 sample portfolios
.venv/bin/python -m scripts.ingest_kb                           # rebuild KB index
.venv/bin/python -m scripts.check_providers                     # day-1 gate: real API keys work?
.venv/bin/pytest --cov                                          # tests, 90% coverage gate
.venv/bin/ruff check src scripts tests && .venv/bin/ruff format src scripts tests
.venv/bin/mypy src scripts                                      # strict
.venv/bin/alembic revision --autogenerate -m "..."              # after model changes
```

Frontend (from `frontend/`):

```bash
npm run dev          # Vite on WEB_PORT, proxies /api to localhost:API_PORT
```

Ports: `WEB_PORT` and `API_PORT` live in both `backend/.env` and `frontend/.env` (defaults
5173/8000; this machine uses 5174/8001). Never hard-code ports or localhost URLs: the backend
derives `frontend_url`, CORS origins and the Google redirect URI from `WEB_PORT`.

```bash
npm test             # Vitest + Testing Library
npm run lint && npm run typecheck && npm run build
```

After changing any backend request/response model, regenerate the frontend types (CI fails if
they drift):

```bash
cd backend && .venv/bin/python -m scripts.export_openapi ../frontend/openapi.json
cd ../frontend && npm run gen:api
```

## Rules that matter

- **Agents reason, services compute.** Every number comes from a tested pure function in
  `core/services`; LLMs only choose tools and explain. Never do financial math in a prompt.
- **Ask for a data type, not a provider.** Use `MarketDataService`; never call Alpaca or
  Alpha Vantage from routers, agents or MCP. New providers go behind the protocols in
  `data/providers/base.py` and the `ProviderChain`.
- **Every market number carries `Freshness`** (`source`, `as_of`, `live|cached|mock`), and the
  UI shows it with `FreshnessBadge`.
- **Degrade, don't crash.** Provider failures fall back to stale cache, then mock data
  (news falls back to empty, never invented). Only definitive errors such as `UnknownSymbol`
  reach the user.
- **User identity comes only from the verified session cookie** (`CurrentUserDep`), never
  from a request body. Scope every user-data query by that id.
- **Secrets live only in `backend/.env`** (see `.env.example`). Non-secret settings go in
  `backend/config.yaml`. Nested values can be overridden with `__`, e.g. `AUTH__MODE=stub`.
  Nothing secret goes to the frontend; the frontend `.env` holds only the dev proxy target.
- **Errors** raise an `AppError` subclass from `core/errors`; handlers render the envelope.
- **Compliance:** educational framing only; no buy/sell/hold recommendations; the disclaimer
  stays visible in the UI.
- **Sign-in modes** (`AUTH__MODE`): `google` (default); `guest` disables Google and
  `POST /auth/guest` creates a new isolated user (`users.is_guest`) per visitor, allowed in
  production; `stub` signs everyone in as one fixed dev user and is refused when
  `app.env=production`. The frontend reads `GET /auth/config` to pick the landing button.
- Tests mock HTTP with `respx` and use fakes for providers and Google; no test touches the
  network. LLMs, embedders and rerankers use the fakes in `tests/fakes.py`
  (`ScriptedChatModel`, `HashEmbedder`, `FixedReranker`). Keep backend coverage at or above 90%.
- **Agents:** every agent extends `BaseAgent` and returns `AgentOutput`; register it in
  `workflow/factory.py`. Tools are an allow-list per agent; tool results come from services.
  Retrieved or provider text goes into prompts wrapped with `as_data` (prompt-injection guard).
- Frontend: feature code lives in `features/<tab>/`; shared UI in `components/`; every view
  needs loading, empty and error states (UI-09). Use generated API types via `src/api/types.ts`.

## Build plan status

- Day 1 (done): repo, config, DB + migrations, Google sign-in + session cookie + auth stub,
  CI, provider layer (Alpaca, Alpha Vantage, mock) with cache, rate limit, retry, circuit
  breaker and freshness, market routes, KB format and loader, chunking, BM25 index, starter
  articles and glossary, React shell with landing, Market index cards and Profile status.
- Day 2 to 3 (done except chat): LLM gateway, LangGraph graph (router, Send fan-out,
  fallback, synthesizer, compliance), Finance Q&A and Market agents, vector embeddings
  (Gemini + OpenAI collections in ChromaDB), hybrid retrieval and reranker. KB at 110
  articles and 259 glossary terms. Still to do: chat endpoint with SSE and the SQLite
  checkpointer (the container uses an in-memory checkpointer for now).
- Day 3 to 5: Portfolio, Goal, News and Tax agents (Tax is served by Q&A until then),
  Portfolio, Market and Goals views, MCP server, KB/Learn API endpoints.
- Day 6 to 7: tests and evals, Learn tab, trace panel, Docker, docs, demo.
