import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import * as navigation from "@/lib/auth/navigation";
import { GUEST, GUEST_MODE, HEALTH, OVERVIEW } from "@/test/fixtures";
import { mockFetch, unauthenticated } from "@/test/mockFetch";
import { renderApp } from "@/test/renderApp";

describe("Guest sign-in (AUTH__MODE=guest)", () => {
  it("offers 'Continue as guest' instead of Google and signs in without a redirect", async () => {
    let signedIn = false;
    const fetchSpy = mockFetch({
      "GET /auth/config": () => ({ body: GUEST_MODE }),
      "GET /me": () => (signedIn ? { body: GUEST } : unauthenticated()),
      "POST /auth/guest": () => {
        signedIn = true;
        return { status: 204 };
      },
      "GET /market/overview": () => ({ body: OVERVIEW }),
    });
    const redirect = vi.spyOn(navigation, "redirectTo");
    renderApp("/");

    const button = await screen.findByRole("button", { name: "Continue as guest" });
    expect(screen.queryByRole("button", { name: /google/i })).not.toBeInTheDocument();

    await userEvent.click(button);
    expect(await screen.findByRole("article", { name: "S&P 500" })).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledWith("/api/v1/auth/guest", expect.objectContaining({ method: "POST" }));
    expect(redirect).not.toHaveBeenCalled();
  });

  it("shows an error if guest sign-in fails", async () => {
    mockFetch({
      "GET /auth/config": () => ({ body: GUEST_MODE }),
      "GET /me": unauthenticated,
      "POST /auth/guest": () => ({
        status: 404,
        body: { error: { code: "not_found", message: "Guest sign-in is not enabled.", retryable: false } },
      }),
    });
    renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: "Continue as guest" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Guest sign-in is not enabled.");
  });

  it("explains when Google sign-in has been turned off", async () => {
    mockFetch({ "GET /auth/config": () => ({ body: GUEST_MODE }), "GET /me": unauthenticated });
    renderApp("/?auth_error=google_disabled");
    expect(await screen.findByRole("alert")).toHaveTextContent(/turned off/i);
  });

  it("labels guest accounts on the profile tab", async () => {
    mockFetch({ "GET /me": () => ({ body: GUEST }), "GET /health": () => ({ body: HEALTH }) });
    renderApp("/profile");
    expect(await screen.findByText("Guest account")).toBeInTheDocument();
    expect(screen.getByText(/can't be recovered/)).toBeInTheDocument();
  });
});
