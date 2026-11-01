import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ApiToken } from "@/api/types";
import { HEALTH, ME } from "@/test/fixtures";
import { mockFetch } from "@/test/mockFetch";
import { renderApp } from "@/test/renderApp";

import { claudeDesktopConfig } from "./claudeDesktopConfig";

const TOKEN: ApiToken = { id: "t1", name: "Laptop", created_at: "2026-10-01T10:00:00Z", last_used_at: null };

describe("Profile: Claude Desktop access", () => {
  it("creates a token, shows it once with the config, then lists it", async () => {
    let tokens: ApiToken[] = [TOKEN];
    let createdName: unknown = null;
    mockFetch({
      "GET /me": () => ({ body: ME }),
      "GET /health": () => ({ body: HEALTH }),
      "GET /me/tokens": () => ({ body: { tokens } }),
      "POST /me/tokens": (init) => {
        createdName = (JSON.parse(String(init?.body)) as { name: string }).name;
        const made = { id: "t2", name: "Claude Desktop", created_at: new Date().toISOString(), last_used_at: null };
        tokens = [made, ...tokens];
        return { status: 201, body: { ...made, token: "fa_pat_secret123" } };
      },
    });
    renderApp("/profile");
    expect(await screen.findByText("Laptop")).toBeInTheDocument();
    expect(screen.getByText(/never used/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Create token" }));
    expect(await screen.findByText(/You won't be able to see it again/)).toBeInTheDocument();
    expect(createdName).toBe("Claude Desktop");
    expect(screen.getByText("fa_pat_secret123")).toBeInTheDocument();
    expect(screen.getByText(/"FINANCE_API_TOKEN": "fa_pat_secret123"/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByText("fa_pat_secret123")).not.toBeInTheDocument();
    const section = screen.getByRole("region", { name: "Claude Desktop access" });
    await waitFor(() => expect(within(section).getAllByRole("listitem")).toHaveLength(2));
  });

  it("revokes a token and shows the empty state", async () => {
    let tokens: ApiToken[] = [TOKEN];
    mockFetch({
      "GET /me": () => ({ body: ME }),
      "GET /health": () => ({ body: HEALTH }),
      "GET /me/tokens": () => ({ body: { tokens } }),
      "DELETE /me/tokens/t1": () => {
        tokens = [];
        return { status: 204 };
      },
    });
    renderApp("/profile");
    await userEvent.click(await screen.findByRole("button", { name: "Revoke Laptop" }));
    expect(await screen.findByText("No active tokens.")).toBeInTheDocument();
  });

  it("shows errors from creating and loading tokens", async () => {
    mockFetch({
      "GET /me": () => ({ body: ME }),
      "GET /health": () => ({ body: HEALTH }),
      "GET /me/tokens": () => ({ status: 503, body: { error: { code: "x", message: "Database down.", retryable: true } } }),
      "POST /me/tokens": () => ({
        status: 422,
        body: { error: { code: "validation_failed", message: "You can have up to 10 active tokens.", retryable: false } },
      }),
    });
    renderApp("/profile");
    expect(await screen.findByText("Couldn't load your tokens")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Create token" }));
    await waitFor(() => expect(screen.getByText("You can have up to 10 active tokens.")).toBeInTheDocument());
  });

  it("builds a Claude Desktop config that runs the MCP server module", () => {
    const config = JSON.parse(claudeDesktopConfig("fa_pat_x", "https://app.test/api/v1")) as {
      mcpServers: { "finance-assistant": { args: string[]; env: Record<string, string> } };
    };
    const server = config.mcpServers["finance-assistant"];
    expect(server.args).toEqual(["-m", "src.mcp_server"]);
    expect(server.env).toMatchObject({ FINANCE_API_URL: "https://app.test/api/v1", FINANCE_API_TOKEN: "fa_pat_x" });
  });
});
