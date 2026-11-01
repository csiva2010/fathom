import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import * as navigation from "@/lib/auth/navigation";
import { HEALTH, ME, OVERVIEW } from "@/test/fixtures";
import { mockFetch, unauthenticated } from "@/test/mockFetch";
import { renderApp } from "@/test/renderApp";

describe("App routing and auth", () => {
  it("shows only the landing page to signed-out visitors", async () => {
    mockFetch({ "GET /me": unauthenticated });
    renderApp("/market");

    expect(await screen.findByRole("button", { name: /sign in with google/i })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/");
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
    expect(screen.getByText(/for education only/i)).toBeInTheDocument();
  });

  it("explains a cancelled sign-in", async () => {
    mockFetch({ "GET /me": unauthenticated });
    renderApp("/?auth_error=cancelled");
    expect(await screen.findByRole("alert")).toHaveTextContent(/cancelled/i);
  });

  it("sends signed-in users to the market tab with index cards and freshness badges", async () => {
    mockFetch({ "GET /me": () => ({ body: ME }), "GET /market/overview": () => ({ body: OVERVIEW }) });
    renderApp("/");

    const spx = await screen.findByRole("article", { name: "S&P 500" });
    expect(within(spx).getByText("5,800.12")).toBeInTheDocument();
    expect(within(spx).getByText(/Live/)).toBeInTheDocument();
    expect(within(spx).getByText("+12.50 (+0.22%)")).toBeInTheDocument();

    const nasdaq = screen.getByRole("article", { name: "Nasdaq Composite" });
    expect(within(nasdaq).getByText(/Sample data/)).toBeInTheDocument();
    expect(within(nasdaq).getByText(/QQQ ETF/)).toBeInTheDocument();

    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getAllByRole("link")).toHaveLength(6);
  });

  it("starts Google sign-in with a full-page redirect to the backend", async () => {
    mockFetch({ "GET /me": unauthenticated });
    const redirect = vi.spyOn(navigation, "redirectTo").mockImplementation(() => undefined);
    renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: /sign in with google/i }));
    expect(redirect).toHaveBeenCalledWith("/api/v1/auth/google/login");
  });

  it("signs out and returns to the landing page", async () => {
    let signedIn = true;
    const fetchSpy = mockFetch({
      "GET /me": () => (signedIn ? { body: ME } : unauthenticated()),
      "GET /market/overview": () => ({ body: OVERVIEW }),
      "POST /auth/logout": () => {
        signedIn = false;
        return { status: 204 };
      },
    });
    renderApp("/market");

    await userEvent.click(await screen.findByRole("button", { name: /sign out/i }));
    expect(await screen.findByRole("button", { name: /sign in with google/i })).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledWith("/api/v1/auth/logout", expect.objectContaining({ method: "POST" }));
  });

  it("shows account details and provider status on the profile tab", async () => {
    mockFetch({ "GET /me": () => ({ body: ME }), "GET /health": () => ({ body: HEALTH }) });
    renderApp("/profile");

    expect(await screen.findByText("ada@example.com")).toBeInTheDocument();
    expect(screen.getByText("Not set yet")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/Alpaca/)).toBeInTheDocument());
    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText(/Not configured, using sample data/)).toBeInTheDocument();
    expect(screen.getByText("Not built yet")).toBeInTheDocument();
  });

  it("renders a placeholder for tabs that ship later", async () => {
    mockFetch({ "GET /me": () => ({ body: ME }) });
    renderApp("/goals");
    expect(await screen.findByText("Coming soon")).toBeInTheDocument();
  });
});
