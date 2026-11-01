"""Day-1 gate check: do our market-data keys work, and does Alpha Vantage cover the indices?

Calls each provider directly (no cache, no mock fallback) and prints what came back.

Usage (from backend/):  python -m scripts.check_providers
"""

from __future__ import annotations

import asyncio

from src.core.config import get_settings
from src.core.errors import AppError
from src.core.services.market.factory import build_http_client, build_providers


async def _check() -> int:
    settings = get_settings()
    failures = 0
    async with build_http_client(settings) as client:
        providers = build_providers(settings, client)
        av = providers.alpha_vantage
        alpaca = providers.alpaca

        print("Alpha Vantage index quotes")
        if not av.configured:
            print("  SKIPPED: ALPHA_VANTAGE_API_KEY is not set")
            failures += 1
        for index in settings.market.indices if av.configured else []:
            try:
                quote = await av.get_index_quote(index.id, index.name, index.av_symbol)
                print(
                    f"  OK   {index.name:<32} {index.av_symbol:<6} {quote.price:>12,.2f}"
                    f"  as of {quote.as_of:%Y-%m-%d}"
                )
            except AppError as error:
                failures += 1
                print(f"  FAIL {index.name:<32} {index.av_symbol:<6} {error.code}: {error.message}")
                print(f"       fallback will use ETF proxy {index.proxy_symbol} via Alpaca")

        print("\nAlpaca quotes (ETF proxies)")
        if not alpaca.configured:
            print("  SKIPPED: ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are not set")
            failures += 1
        else:
            proxies = [i.proxy_symbol for i in settings.market.indices]
            try:
                quotes = await alpaca.get_quotes(proxies)
                for symbol in proxies:
                    proxy_quote = quotes.get(symbol)
                    if proxy_quote is None:
                        failures += 1
                        print(f"  FAIL {symbol:<6} missing from response")
                    else:
                        print(
                            f"  OK   {symbol:<6} {proxy_quote.price:>12,.2f}"
                            f"  as of {proxy_quote.as_of:%Y-%m-%d %H:%M}"
                        )
            except AppError as error:
                failures += 1
                print(f"  FAIL {error.code}: {error.message}")

    print("\nResult:", "all checks passed" if failures == 0 else f"{failures} problem(s)")
    return 0 if failures == 0 else 1


def main() -> int:
    return asyncio.run(_check())


if __name__ == "__main__":
    raise SystemExit(main())
