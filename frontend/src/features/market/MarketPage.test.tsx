import { screen } from "@testing-library/react";
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
});
