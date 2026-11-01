import type { GoalType, RiskProfileName } from "@/api/types";

export const GOAL_TYPES: { value: GoalType; label: string }[] = [
  { value: "retirement", label: "Retirement" },
  { value: "house", label: "Home purchase" },
  { value: "emergency", label: "Emergency fund" },
  { value: "education", label: "Education" },
  { value: "other", label: "Other" },
];

export function goalTitle(goal: { name: string; type: GoalType }): string {
  return goal.name || GOAL_TYPES.find((t) => t.value === goal.type)?.label || "Goal";
}

export const RISK_PROFILES: { value: RiskProfileName; label: string; blurb: string }[] = [
  { value: "conservative", label: "Conservative", blurb: "Prefers steadiness; accepts lower expected growth for smaller swings." },
  { value: "moderate", label: "Moderate", blurb: "Balances growth and stability; can ride out ordinary market drops." },
  { value: "aggressive", label: "Aggressive", blurb: "Aims for long-term growth and can tolerate large, lasting swings." },
];
