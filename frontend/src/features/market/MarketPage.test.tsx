import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ME, OVERVIEW } from "@/test/fixtures";
import { mockFetch } from "@/test/mockFetch";
import { renderApp } from "@/test/renderApp";

describe("MarketPage", () => {
  it("shows a retryable error state, then recovers", async () => {
    let calls = 0;
    mockFetch({
      "GET /me": () => ({ body: ME }),
      "GET /market/overview": () => {
        calls += 1;
        return calls === 1
          ? { status: 502, body: { error: { code: "provider_unavailable", message: "Data provider is down.", retryable: true } } }
          : { body: OVERVIEW };
      },
    });
    renderApp("/market");

    expect(await screen.findByText("Data provider is down.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByRole("article", { name: "S&P 500" })).toBeInTheDocument();
  });

  it("shows an empty state when no indexes are configured", async () => {
    mockFetch({ "GET /me": () => ({ body: ME }), "GET /market/overview": () => ({ body: { indices: [] } }) });
    renderApp("/market");
    expect(await screen.findByText("No indexes configured")).toBeInTheDocument();
  });

  it("follows a watchlist, charts a ticker by range, and lists movers and sectors", async () => {
    const NOW = new Date().toISOString();
    const FRESH = { source: "mock", as_of: NOW, status: "mock" as const };
    const quote = (symbol: string, price: number, change_percent: number) => ({
      quote: { symbol, price, change: price * change_percent / 100, change_percent, as_of: NOW },
      freshness: FRESH,
    });
    const historyRanges: string[] = [];
    window.localStorage.setItem("fathom.watchlist.u1", JSON.stringify(["AAPL"]));
    mockFetch({
      "GET /me": () => ({ body: ME }),
      "GET /market/overview": () => ({ body: OVERVIEW }),
      "GET /market/quotes": () => ({ body: { quotes: [quote("AAPL", 225.41, -1.35), quote("MSFT", 410, 0.5)], unknown_symbols: [] } }),
      "GET /market/history/AAPL": () => ({
        body: {
          history: { symbol: "AAPL", range: "6M", timeframe: "1Day", bars: [200, 210, 225].map((c, i) => ({ t: `2026-0${i + 1}-02T00:00:00Z`, open: c, high: c, low: c, close: c, volume: 1 })) },
          freshness: FRESH,
        },
      }),
      "GET /market/history/MSFT": () => ({ body: { history: { symbol: "MSFT", range: "6M", timeframe: "1Day", bars: [] }, freshness: FRESH } }),
      "GET /market/indicators/AAPL": () => ({
        body: { indicators: { symbol: "AAPL", last_close: 225, as_of: NOW, price_vs_sma_50_percent: 3.2, price_vs_sma_200_percent: 8.1, week52_low: 160, week52_high: 240, volatility_30d_percent: 24.5, bars_used: 250 }, freshness: FRESH },
      }),
      "GET /market/indicators/MSFT": () => ({ status: 404, body: { error: { code: "unknown_symbol", message: "No data.", retryable: false } } }),
      "GET /market/symbols": () => ({ body: { results: [{ symbol: "MSFT", name: "Microsoft Corp", exchange: "NASDAQ" }], freshness: FRESH } }),
      "GET /market/movers": () => ({ body: { gainers: [quote("NVDA", 900, 4.1)], losers: [quote("TSLA", 200, -3.3)] } }),
      "GET /market/sectors": () => ({ body: { sectors: [{ sector: { sector: "Energy", symbol: "XLE", price: 90, change_percent: 1.2 }, freshness: FRESH }] } }),
    });
    const spy = globalThis.fetch as unknown as { mock: { calls: [RequestInfo][] } };
    renderApp("/market");

    const watchlist = await screen.findByRole("region", { name: "Watchlist" });
    expect(await within(watchlist).findByText("225.41")).toBeInTheDocument();
    expect(await screen.findByRole("figure", { name: "AAPL closing prices, 6M" })).toBeInTheDocument();
    expect(await screen.findByText("+8.1%")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "1Y" }));
    await waitFor(() => {
      for (const [url] of spy.mock.calls) if (String(url).includes("/history/")) historyRanges.push(String(url));
      expect(historyRanges.some((u) => u.endsWith("range=1Y"))).toBe(true);
    });

    await userEvent.type(within(watchlist).getByLabelText("Add a ticker"), "micro");
    await userEvent.click(await screen.findByRole("button", { name: "MSFT, Microsoft Corp" }));
    expect(JSON.parse(window.localStorage.getItem("fathom.watchlist.u1") ?? "[]")).toEqual(["AAPL", "MSFT"]);
    expect(window.location.search).toBe("?symbol=MSFT");
    expect(await screen.findByText("No price history for this range.")).toBeInTheDocument();

    const movers = screen.getByRole("region", { name: "Today's movers" });
    expect(within(movers).getByText("+4.10%")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Sectors today" })).toHaveTextContent("Energy");

    await userEvent.click(within(watchlist).getByRole("button", { name: "Remove AAPL" }));
    expect(JSON.parse(window.localStorage.getItem("fathom.watchlist.u1") ?? "[]")).toEqual(["MSFT"]);
    window.localStorage.clear();
  });
});
