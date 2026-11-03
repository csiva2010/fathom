import type { AuthConfig, Health, MarketOverview, Me, TraceStep } from "@/api/types";

export const ME: Me = {
  id: "u1",
  email: "ada@example.com",
  name: "Ada Lovelace",
  avatar_url: null,
  is_guest: false,
  profile: {
    experience_level: "beginner",
    risk_profile: null,
    risk_answers: null,
    disclaimer_accepted_at: null,
    onboarding_complete: false,
  },
};

const NOW = new Date().toISOString();

export const OVERVIEW: MarketOverview = {
  indices: [
    {
      index: { id: "SPX", name: "S&P 500", symbol: "SPX", is_proxy: false, price: 5800.12, change: 12.5, change_percent: 0.22, as_of: NOW },
      freshness: { source: "alpha_vantage", as_of: NOW, status: "live" },
    },
    {
      index: { id: "IXIC", name: "Nasdaq Composite", symbol: "QQQ", is_proxy: true, price: 495.1, change: -3.2, change_percent: -0.64, as_of: NOW },
      freshness: { source: "mock", as_of: NOW, status: "mock" },
    },
  ],
};

export const HEALTH: Health = {
  status: "ok",
  version: "0.1.0",
  env: "development",
  auth_mode: "stub",
  database: true,
  knowledge_index: false,
  providers: [
    { name: "alpaca", configured: true, circuit: "closed" },
    { name: "alpha_vantage", configured: false, circuit: "closed" },
  ],
};

export const GUEST: Me = { ...ME, id: "g1", email: "", name: "Guest", is_guest: true };

export const GUEST_MODE: AuthConfig = { mode: "guest", google_enabled: false, guest_enabled: true };

/** A workflow trace step with zero usage unless given ("How I answered" tests). */
export function traceStep(node: string, latency_ms: number, extra: Partial<TraceStep> = {}): TraceStep {
  return { node, latency_ms, llm_calls: 0, input_tokens: 0, output_tokens: 0, fallbacks: 0, ...extra };
}
