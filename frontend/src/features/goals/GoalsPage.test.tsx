import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ME } from "@/test/fixtures";
import { mockFetch } from "@/test/mockFetch";
import { renderApp } from "@/test/renderApp";
import { GOAL, projection, QUESTIONS } from "@/test/viewFixtures";

const WITH_PROFILE = { ...ME, profile: { ...ME.profile, risk_profile: "moderate" as const } };

describe("Goals", () => {
  it("scores the risk questionnaire on the server and shows the profile", async () => {
    let submitted: unknown = null;
    mockFetch({
      "GET /me": () => ({ body: ME }),
      "GET /goals": () => ({ body: { goals: [] } }),
      "GET /me/risk-questionnaire": () => ({ body: { questions: QUESTIONS } }),
      "POST /me/risk-questionnaire": (init) => {
        submitted = JSON.parse(String(init?.body));
        return { body: { result: { score: 6, max_score: 6, risk_profile: "aggressive" }, me: { ...ME, profile: { ...ME.profile, risk_profile: "aggressive" } } } };
      },
    });
    renderApp("/goals");
    expect(await screen.findByText("No goals yet")).toBeInTheDocument();
    const submit = await screen.findByRole("button", { name: "See my profile" });
    expect(submit).toBeDisabled();
    await userEvent.click(screen.getByLabelText("horizon option d"));
    await userEvent.click(screen.getByLabelText("drop_reaction option d"));
    await userEvent.click(submit);
    expect(await screen.findByText("Aggressive.")).toBeInTheDocument();
    expect(submitted).toEqual({ answers: { horizon: "d", drop_reaction: "d" } });
  });

  it("projects a goal and recalculates as the contribution slider moves", async () => {
    const requests: number[] = [];
    let saved: unknown = null;
    mockFetch({
      "GET /me": () => ({ body: WITH_PROFILE }),
      "GET /goals": () => ({ body: { goals: [GOAL] } }),
      "POST /goals/project": (init) => {
        const body = JSON.parse(String(init?.body)) as { monthly_contribution: number };
        requests.push(body.monthly_contribution);
        return {
          body: {
            projection: projection(body.monthly_contribution),
            example_allocation: { risk_profile: "moderate", slices: [{ asset_class: "stocks", weight: 0.6 }], note: "A generic textbook example." },
          },
        };
      },
      "PUT /goals/g1": (init) => {
        saved = JSON.parse(String(init?.body));
        return { body: GOAL };
      },
    });
    renderApp("/goals");

    const detail = await screen.findByRole("region", { name: "Starter home" });
    expect(within(detail).getByRole("figure")).toBeInTheDocument();
    expect(await screen.findByText(/Example moderate mix/)).toBeInTheDocument();
    expect(within(detail).getByText("$22,500", { selector: "strong" })).toBeInTheDocument();

    fireEvent.change(within(detail).getByLabelText(/Monthly contribution/), { target: { value: "1000" } });
    await waitFor(() => expect(requests).toContain(1000));
    expect(await within(detail).findByText("$45,000", { selector: "strong" })).toBeInTheDocument();
    await userEvent.click(within(detail).getByRole("button", { name: "Save $1,000 a month" }));
    await waitFor(() => expect(saved).toMatchObject({ monthly_contribution: 1000, risk_profile: "moderate" }));
  });

  it("adds a goal and shows server validation errors", async () => {
    let attempts = 0;
    mockFetch({
      "GET /me": () => ({ body: WITH_PROFILE }),
      "GET /goals": () => ({ body: { goals: attempts > 1 ? [GOAL] : [] } }),
      "POST /goals": () => {
        attempts += 1;
        return attempts === 1
          ? { status: 422, body: { error: { code: "validation_failed", message: "The goal's target date must be in the future.", retryable: false } } }
          : { status: 201, body: GOAL };
      },
      "POST /goals/project": () => ({ body: { projection: projection(500), example_allocation: { risk_profile: "moderate", slices: [], note: "" } } }),
    });
    renderApp("/goals");
    await userEvent.click(await screen.findByRole("button", { name: "Add your first goal" }));
    await userEvent.type(screen.getByLabelText("Target amount ($)"), "60000");
    await userEvent.click(screen.getByRole("button", { name: "Add goal" }));
    expect(await screen.findByText("The goal's target date must be in the future.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add goal" }));
    expect(await screen.findByRole("region", { name: "Starter home" })).toBeInTheDocument();
  });

  it("shows an error state when goals fail to load", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    mockFetch({
      "GET /me": () => ({ body: WITH_PROFILE }),
      "GET /goals": () => ({ status: 503, body: { error: { code: "down", message: "Database unavailable.", retryable: true } } }),
    });
    renderApp("/goals");
    expect(await screen.findByText("Couldn't load your goals")).toBeInTheDocument();
  });
});
