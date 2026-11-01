import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ME } from "@/test/fixtures";
import { mockFetch } from "@/test/mockFetch";
import { renderApp } from "@/test/renderApp";
import { ANALYSIS, SAMPLE } from "@/test/viewFixtures";

describe("Portfolio", () => {
  it("analyzes a sample with metrics, donut, sectors, benchmark line and learning points", async () => {
    const ranges: string[] = [];
    mockFetch({
      "GET /me": () => ({ body: ME }),
      "GET /portfolios": () => ({ body: { portfolios: [SAMPLE] } }),
      "GET /portfolios/s1/analysis": () => ({ body: ANALYSIS }),
    });
    const spy = vi.mocked(globalThis.fetch);
    renderApp("/portfolio");

    const metrics = await screen.findByRole("region", { name: "Key metrics" });
    expect(within(metrics).getByText("$3,200")).toBeInTheDocument();
    expect(within(metrics).getByText("72/100")).toBeInTheDocument();
    expect(within(metrics).getByText(/in line with your moderate profile/)).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Allocation by asset class legend" })).toHaveTextContent("Stock funds (ETFs)87.5%");
    expect(screen.getByRole("list", { name: "Sector exposure" })).toHaveTextContent("Information Technology");
    expect(screen.getByRole("figure", { name: /compared with S&P 500/ })).toBeInTheDocument();
    expect(screen.getByText("Bonds and cash usually swing less than stocks.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy and edit" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "5Y" }));
    await waitFor(() => {
      for (const [url] of spy.mock.calls) if (String(url).includes("analysis")) ranges.push(new URL(String(url), "http://x").searchParams.get("range") ?? "");
      expect(ranges).toContain("5Y");
    });
  });

  it("builds a portfolio from a CSV, shows row problems and saves it", async () => {
    let saved: { name: string; holdings: unknown[] } | null = null;
    const mine = { ...SAMPLE, id: "p1", name: "My mix", is_sample: false };
    mockFetch({
      "GET /me": () => ({ body: ME }),
      "GET /portfolios": () => ({ body: { portfolios: saved ? [mine, SAMPLE] : [SAMPLE] } }),
      "GET /portfolios/s1/analysis": () => ({ body: ANALYSIS }),
      "GET /portfolios/p1/analysis": () => ({ body: ANALYSIS }),
      "POST /portfolios/import": () => ({
        body: { holdings: [{ symbol: "AAPL", quantity: 3, cost_basis: 150, asset_class: null }], errors: ["Row 3: 'bad!' isn't a valid ticker."] },
      }),
      "POST /portfolios": (init) => {
        saved = JSON.parse(String(init?.body)) as { name: string; holdings: unknown[] };
        return { status: 201, body: mine };
      },
    });
    renderApp("/portfolio");
    await userEvent.click(await screen.findByRole("button", { name: "New portfolio" }));
    await userEvent.type(screen.getByLabelText("Name"), "My mix");
    const file = new File(["Symbol,Quantity\nAAPL,3\nbad!,1\n"], "holdings.csv", { type: "text/csv" });
    fireEvent.change(screen.getByLabelText("CSV file"), { target: { files: [file] } });

    expect(await screen.findByText("Row 3: 'bad!' isn't a valid ticker.")).toBeInTheDocument();
    expect(screen.getByLabelText("Ticker 1")).toHaveValue("AAPL");
    await userEvent.click(screen.getByRole("button", { name: "Save portfolio" }));
    await waitFor(() => expect(saved).toEqual({ name: "My mix", description: "", holdings: [{ symbol: "AAPL", quantity: 3, cost_basis: 150, asset_class: null }] }));
    expect(await screen.findByRole("heading", { name: "My mix" })).toBeInTheDocument();
  });

  it("shows the empty state with no portfolios and an error when saving fails", async () => {
    mockFetch({
      "GET /me": () => ({ body: ME }),
      "GET /portfolios": () => ({ body: { portfolios: [] } }),
      "POST /portfolios": () => ({ status: 422, body: { error: { code: "validation_failed", message: "We couldn't find APPL (did you mean AAPL?).", retryable: false } } }),
    });
    renderApp("/portfolio");
    expect(await screen.findByText("Add your first portfolio")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "New portfolio" }));
    await userEvent.type(screen.getByLabelText("Name"), "Typos");
    await userEvent.type(screen.getByLabelText("Ticker 1"), "APPL");
    await userEvent.type(screen.getByLabelText("Shares 1"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Save portfolio" }));
    expect(await screen.findByText(/did you mean AAPL/)).toBeInTheDocument();
  });
});
