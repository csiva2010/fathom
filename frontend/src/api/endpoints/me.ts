import { apiFetch } from "../client";
import type { Me, ProfileUpdate, RiskAssessment, RiskQuestion } from "../types";

export function getMe(): Promise<Me> {
  return apiFetch<Me>("/me");
}

export function updateProfile(update: ProfileUpdate): Promise<Me> {
  return apiFetch<Me>("/me/profile", { method: "PUT", body: JSON.stringify(update) });
}

export function getRiskQuestionnaire(): Promise<{ questions: RiskQuestion[] }> {
  return apiFetch<{ questions: RiskQuestion[] }>("/me/risk-questionnaire");
}

export function submitRiskQuestionnaire(answers: Record<string, string>): Promise<RiskAssessment> {
  return apiFetch<RiskAssessment>("/me/risk-questionnaire", { method: "POST", body: JSON.stringify({ answers }) });
}
