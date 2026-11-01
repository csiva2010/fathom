import { apiFetch } from "../client";
import type { CsvImport, PortfolioAnalysis, PortfolioIn, PortfolioOut, PriceRange } from "../types";

export function listPortfolios(): Promise<{ portfolios: PortfolioOut[] }> {
  return apiFetch<{ portfolios: PortfolioOut[] }>("/portfolios");
}

export function createPortfolio(body: PortfolioIn): Promise<PortfolioOut> {
  return apiFetch<PortfolioOut>("/portfolios", { method: "POST", body: JSON.stringify(body) });
}

export function updatePortfolio(id: string, body: PortfolioIn): Promise<PortfolioOut> {
  return apiFetch<PortfolioOut>(`/portfolios/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(body) });
}

export async function deletePortfolio(id: string): Promise<void> {
  await apiFetch<undefined>(`/portfolios/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function importCsv(content: string): Promise<CsvImport> {
  return apiFetch<CsvImport>("/portfolios/import", { method: "POST", body: JSON.stringify({ content }) });
}

export function getAnalysis(id: string, range: PriceRange): Promise<PortfolioAnalysis> {
  return apiFetch<PortfolioAnalysis>(`/portfolios/${encodeURIComponent(id)}/analysis?range=${range}`);
}
