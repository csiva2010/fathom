"""Load the three preloaded sample portfolios (PF-01). Idempotent.

Usage (from backend/):  python -m scripts.seed_db
"""

from __future__ import annotations

from src.core.config import get_settings, resolve_path
from src.data.db.repositories.portfolio_repository import HoldingInput, PortfolioRepository
from src.data.db.session import create_db_engine, create_session_factory, session_scope
from src.data.providers.mock.seed_loader import SeedData


def main() -> int:
    settings = get_settings()
    seed = SeedData(resolve_path(settings.seed.dir))
    factory = create_session_factory(create_db_engine(settings))

    for session in session_scope(factory):
        repo = PortfolioRepository(session)
        for sample in seed.sample_portfolios:
            portfolio = repo.upsert_sample(
                name=sample["name"],
                description=sample.get("description", ""),
                holdings=[HoldingInput(**h) for h in sample["holdings"]],
            )
            print(f"seeded sample portfolio: {portfolio.name} ({len(portfolio.holdings)} holdings)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
