import type { AgentName } from "@/api/types";

/** Display names for the six agents (CH-03). */
export const AGENT_LABELS: Record<AgentName, string> = {
  finance_qa: "Finance Q&A",
  portfolio_analysis: "Portfolio Analysis",
  market_analysis: "Market Analysis",
  goal_planning: "Goal Planning",
  news_synthesizer: "News",
  tax_education: "Tax Education",
};
