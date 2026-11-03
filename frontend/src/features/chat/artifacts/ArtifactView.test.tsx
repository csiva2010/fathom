import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Artifact } from "@/api/types";

import { ArtifactView } from "./ArtifactView";

const NOW = "2026-10-30T20:00:00Z";
const LIVE = { source: "alpaca", as_of: NOW, status: "live" as const };
const MOCK = { source: "mock", as_of: NOW, status: "mock" as const };

function show(artifact: Artifact) {
  render(<ArtifactView artifact={artifact} />);
  return screen.getByRole("region", { name: artifact.title });
}

describe("ArtifactView", () => {
  it("renders a quote card", () => {
    const card = show({
      kind: "quote_card",
      title: "SPY",
      data: { quote: { symbol: "SPY", price: 571.2, change: 2.5, change_percent: 0.44, as_of: NOW }, freshness: LIVE },
    });
    expect(card).toHaveTextContent("571.20");
    expect(card).toHaveTextContent("+2.50 (+0.44%)");
  });

  it("renders indicators with gaps as n/a", () => {
    const card = show({
      kind: "indicators",
      title: "AAPL indicators",
      data: { price_vs_sma_50_percent: 1.5, price_vs_sma_200_percent: null, week52_low: 160, week52_high: 240, volatility_30d_percent: 22.4, freshness: LIVE },
    });
    expect(within(card).getByText("160.00–240.00")).toBeInTheDocument();
    expect(within(card).getByText("n/a")).toBeInTheDocument();
    expect(card).toHaveTextContent("22.4%");
  });

  it("renders index cards, movers and sectors", () => {
    show({
      kind: "index_cards",
      title: "Major indices",
      data: {
        indices: [
          { value: { id: "spx", name: "S&P 500", symbol: "SPY", is_proxy: true, price: 571.2, change: -1, change_percent: -0.2 }, freshness: LIVE },
          { value: { id: "dji", name: "Dow", symbol: "DJI", is_proxy: false, price: 42000, change: 0, change_percent: 0 }, freshness: MOCK },
        ],
      },
    });
    expect(screen.getByText("S&P 500 (via SPY)")).toBeInTheDocument();
    expect(screen.getByText("Dow")).toBeInTheDocument();

    const movers = show({
      kind: "movers",
      title: "Today's movers",
      data: {
        gainers: [{ value: { symbol: "NVDA", price: 1, change_percent: 4.2, as_of: NOW }, freshness: LIVE }],
        losers: [{ value: { symbol: "TSLA", price: 1, change_percent: null, as_of: NOW }, freshness: LIVE }],
      },
    });
    expect(movers).toHaveTextContent("NVDA+4.20%");
    expect(movers).toHaveTextContent("TSLA—");

    const sectors = show({
      kind: "sector_table",
      title: "Sectors",
      data: { sectors: [{ sector: "Technology", symbol: "XLK", change_percent: 1.25 }, { sector: "Energy", symbol: "XLE", change_percent: null }] },
    });
    expect(within(sectors).getAllByRole("row")).toHaveLength(3);
    expect(sectors).toHaveTextContent("+1.25%");
  });

  it("renders a price chart", () => {
    show({
      kind: "price_chart",
      title: "QQQ",
      data: {
        points: [
          { t: "2026-10-01", close: 480 },
          { t: "2026-10-15", close: 490 },
          { t: "2026-10-30", close: 496 },
        ],
        freshness: LIVE,
      },
    });
    expect(screen.getByRole("figure", { name: "QQQ closing prices" })).toBeInTheDocument();
  });

  it("renders portfolio metrics with a benchmark and allocation bars", () => {
    const metrics = show({
      kind: "portfolio_metrics",
      title: "Your portfolio",
      data: {
        total_value: 25000,
        total_gain: 3000,
        total_gain_percent: 13.6,
        diversification_score: 42,
        weighted_beta: 1.21,
        volatility_percent: 24.5,
        max_drawdown_percent: -31.2,
        weighted_expense_ratio: 0.0012,
        benchmark: { benchmark_symbol: "SPY", range: "1Y", portfolio_return_percent: 18.2, benchmark_return_percent: 15.1 },
        freshness: [LIVE, LIVE],
      },
    });
    expect(metrics).toHaveTextContent("$25,000");
    expect(metrics).toHaveTextContent("42/100");
    expect(metrics).toHaveTextContent("1.21");
    expect(metrics).toHaveTextContent("31.2%");
    expect(metrics).toHaveTextContent("for SPY");

    const empty = show({ kind: "portfolio_metrics", title: "Nothing priced", data: { benchmark: null, freshness: [] } });
    expect(within(empty).getAllByText("n/a")).toHaveLength(4);

    show({
      kind: "allocation",
      title: "Allocation",
      data: {
        by_asset_class: [{ label: "etf", value: 15000, weight: 0.6 }, { label: "crypto", value: 10000, weight: 0.4 }],
        by_sector: [{ label: "Technology", value: 20000, weight: 0.8 }],
        freshness: [LIVE],
      },
    });
    expect(screen.getByText("Stock funds (ETFs)")).toBeInTheDocument();
    expect(screen.getByText("crypto")).toBeInTheDocument();
    expect(screen.getByText("Technology")).toBeInTheDocument();
  });

  it("renders a goal projection and an example allocation", () => {
    const series = [0, 30, 60].map((month) => ({
      month,
      date: `2027-0${1 + month / 30}-01`,
      contributed: 10000 + month * 600,
      values: { pessimistic: 10000 + month * 610, expected: 10000 + month * 640, optimistic: 10000 + month * 680 },
    }));
    const projection = show({
      kind: "projection",
      title: "House goal",
      data: {
        target_amount: 50000,
        series,
        assumptions: "Returns compound monthly.",
        scenarios: [
          { scenario: "optimistic", annual_return_percent: 7, final_value: 52000, final_value_real: 46000, reaches_target: true, required_monthly_contribution: 560 },
          { scenario: "pessimistic", annual_return_percent: 2, final_value: 46000, final_value_real: 41000, reaches_target: false, required_monthly_contribution: 680 },
          { scenario: "expected", annual_return_percent: 5, final_value: 50500, final_value_real: 44500, reaches_target: true, required_monthly_contribution: 595 },
        ],
      },
    });
    const rows = within(projection).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.textContent?.split(" (")[0])).toEqual(["expected", "pessimistic", "optimistic"]);
    expect(within(projection).getByText("short of target")).toBeInTheDocument();
    expect(projection).toHaveTextContent("Returns compound monthly.");

    const example = show({
      kind: "example_allocation",
      title: "Example moderate mix",
      data: { slices: [{ asset_class: "stocks", weight: 0.6 }, { asset_class: "bonds", weight: 0.4 }], note: "A textbook mix, not advice." },
    });
    expect(example).toHaveTextContent("Stocks");
    expect(example).toHaveTextContent("A textbook mix, not advice.");
  });

  it("renders news, linking only items with a URL", () => {
    const news = show({
      kind: "news_list",
      title: "AAPL news",
      data: {
        items: [
          { id: "1", headline: "Apple reports earnings", source: "Reuters", url: "https://example.com/a", published_at: NOW },
          { id: "2", headline: "No link here", source: "", url: "", published_at: NOW },
        ],
        freshness: LIVE,
      },
    });
    expect(within(news).getByRole("link", { name: "Apple reports earnings" })).toHaveAttribute("href", "https://example.com/a");
    expect(within(news).queryByRole("link", { name: "No link here" })).not.toBeInTheDocument();
    expect(news).toHaveTextContent("Reuters · Oct 30");
  });

  it("renders screenshot holdings with live prices and what couldn't be priced", () => {
    const table = show({
      kind: "screenshot_holdings",
      title: "From your screenshot",
      data: {
        rows: [
          { symbol: "VTI", name: "Vanguard Total Stock", quantity: 12.5, screenshot_price: 280, live_price: 285.1, market_value: 3563.75 },
          { symbol: "ZZZZ", name: "", quantity: 3, screenshot_price: null, live_price: null, market_value: null },
        ],
        unpriced: ["ZZZZ"],
        freshness: [LIVE],
      },
    });
    expect(table).toHaveTextContent("Vanguard Total Stock");
    expect(table).toHaveTextContent("285.10");
    expect(table).toHaveTextContent("$3,564");
    expect(table).toHaveTextContent("Couldn't price: ZZZZ.");
  });

  it("hides malformed payloads and unknown kinds instead of breaking the chat", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { container } = render(<ArtifactView artifact={{ kind: "quote_card", title: "Broken", data: {} }} />);
    expect(container).toBeEmptyDOMElement();
    const unknown = { kind: "hologram", title: "?", data: {} } as unknown as Artifact;
    const { container: other } = render(<ArtifactView artifact={unknown} />);
    expect(other).toBeEmptyDOMElement();
  });
});
