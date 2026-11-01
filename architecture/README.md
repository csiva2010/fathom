# Architecture diagrams

Standalone HTML diagrams (open in a browser; dark/light themes, export to SVG/PNG).
Generated with Archify from the JSON sources in `candidates/`, pinned to commit `841f756`.

| Diagram | What it shows |
|---|---|
| [system-architecture.html](system-architecture.html) | End-to-end system: SPA, FastAPI, LangGraph, agents, services, providers, RAG, SQLite, MCP |
| [page-landing-signin.html](page-landing-signin.html) | Landing page: auth config, Google / guest sign-in, session cookie |
| [page-chat.html](page-chat.html) | Chat: SSE turn through router, agent fan-out, synthesizer, compliance |
| [page-portfolio.html](page-portfolio.html) | Portfolio: list, analysis, CSV import and save |
| [page-market.html](page-market.html) | Market: watchlist, overview, history and indicators, provider fallback |
| [page-goals.html](page-goals.html) | Goals: risk questionnaire, live projection slider, save |
| [page-learn.html](page-learn.html) | Learn: article catalog, article view, glossary |
| [page-profile.html](page-profile.html) | Profile: health, access tokens, Claude Desktop (MCP) use, sign out |

To regenerate one, edit its JSON in `candidates/` and run Archify `finalize` with `--repo-root ..`.
