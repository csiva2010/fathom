import type { Article, ArticleList, ArticleSummary, Goal, PortfolioAnalysis, PortfolioOut, RiskQuestion } from "@/api/types";

const NOW = new Date().toISOString();
export const FRESH = { source: "mock", as_of: NOW, status: "mock" as const };

function inYears(years: number): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() + years);
  return d.toISOString().slice(0, 10);
}

const SERIES = [0, 12, 24].map((month) => ({
  month,
  date: inYears(month / 12),
  contributed: 10000 + 500 * month,
  values: { pessimistic: 10000 + 480 * month, expected: 10000 + 520 * month, optimistic: 10000 + 560 * month },
}));

export function projection(monthly: number) {
  const scale = monthly / 500;
  return {
    months: 24,
    target_amount: 60000,
    target_amount_real: 57000,
    inflation_percent: 2.5,
    total_contributed: 10000 + monthly * 24,
    scenarios: [
      { scenario: "pessimistic" as const, annual_return_percent: 1.5, final_value: 21000 * scale, final_value_real: 20000, reaches_target: false, shortfall: 39000, required_monthly_contribution: 2050 },
      { scenario: "expected" as const, annual_return_percent: 5.5, final_value: 22500 * scale, final_value_real: 21400, reaches_target: false, shortfall: 37500, required_monthly_contribution: 1980 },
      { scenario: "optimistic" as const, annual_return_percent: 8, final_value: 23500 * scale, final_value_real: 22300, reaches_target: false, shortfall: 36500, required_monthly_contribution: 1930 },
    ],
    series: SERIES,
    assumptions: "Illustrative assumptions, not predictions.",
  };
}

export const GOAL: Goal = {
  id: "g1",
  type: "house",
  name: "Starter home",
  target_amount: 60000,
  target_date: inYears(2),
  current_savings: 10000,
  monthly_contribution: 500,
  risk_profile: "moderate",
  created_at: NOW,
  projection: projection(500),
  projection_error: null,
};

export const QUESTIONS: RiskQuestion[] = ["horizon", "drop_reaction"].map((id) => ({
  id,
  prompt: `Question ${id}?`,
  options: ["a", "b", "c", "d"].map((o, i) => ({ id: o, label: `${id} option ${o}`, points: i })),
}));

export const SAMPLE: PortfolioOut = {
  id: "s1",
  name: "Three-Fund Starter",
  description: "A simple mix.",
  is_sample: true,
  created_at: NOW,
  holdings: [
    { symbol: "VTI", quantity: 10, cost_basis: 200, asset_class: "etf" },
    { symbol: "BND", quantity: 5, cost_basis: null, asset_class: "bond_etf" },
  ],
};

export const ANALYSIS: PortfolioAnalysis = {
  total_value: 3200,
  total_cost: 2000,
  total_gain: 400,
  total_gain_percent: 20,
  holdings: [
    { symbol: "VTI", name: "Vanguard Total Stock Market", asset_class: "etf", quantity: 10, price: 280, market_value: 2800, cost_value: 2000, gain: 800, gain_percent: 40, weight: 0.875, sector: null, beta: 1, expense_ratio: 0.0003 },
    { symbol: "BND", name: "Vanguard Total Bond", asset_class: "bond_etf", quantity: 5, price: 80, market_value: 400, cost_value: null, gain: null, gain_percent: null, weight: 0.125, sector: null, beta: 0.1, expense_ratio: 0.0003 },
  ],
  allocation_by_holding: [],
  allocation_by_asset_class: [
    { label: "etf", value: 2800, weight: 0.875 },
    { label: "bond_etf", value: 400, weight: 0.125 },
  ],
  allocation_by_sector: [
    { label: "Information Technology", value: 900, weight: 0.28 },
    { label: "Fixed Income", value: 400, weight: 0.125 },
  ],
  weighted_expense_ratio: 0.0003,
  diversification: { score: 72, effective_holdings: 18, effective_sectors: 7, largest_holding: "VTI", largest_holding_weight: 0.875, largest_sector: "Information Technology", largest_sector_weight: 0.28, drivers: ["Largest position: VTI at 88% of the portfolio."] },
  risk: { weighted_beta: 0.89, beta_coverage: 1, annualized_volatility_percent: 13.2, max_drawdown_percent: -11.5, history_days: 250, risk_level: "moderate", profile: "moderate", profile_fit: "within" },
  benchmark: { benchmark_symbol: "SPY", range: "1Y", start: "2025-11-01", end: "2026-10-30", portfolio_return_percent: 9.5, benchmark_return_percent: 12.1, difference_percent: -2.6 },
  performance: [
    { date: "2025-11-01", portfolio: 100, benchmark: 100 },
    { date: "2026-04-01", portfolio: 104, benchmark: 106 },
    { date: "2026-10-30", portfolio: 109.5, benchmark: 112.1 },
  ],
  observations: [{ code: "all_equity", message: "Bonds and cash usually swing less than stocks." }],
  unpriced: [],
  freshness: [FRESH],
};

const WASH_SALE: ArticleSummary = {
  id: "wash-sale-rule",
  title: "The Wash Sale Rule",
  category: "tax",
  category_label: "Tax",
  level: "intermediate",
  summary: "Stops investors from selling at a loss just to claim a deduction.",
  tags: ["wash sale"],
  source_name: "IRS",
  source_url: "https://www.irs.gov/p550",
  last_reviewed: "2026-10-31",
  reading_minutes: 2,
};

export const ARTICLES: ArticleList = {
  articles: [
    WASH_SALE,
    { id: "index-funds", title: "Index Funds", category: "funds_etfs", category_label: "Funds & ETFs", level: "beginner", summary: "A fund that tracks a market index.", tags: [], source_name: "SEC", source_url: "https://www.investor.gov", last_reviewed: "2026-10-31", reading_minutes: 1 },
  ],
  categories: [
    { id: "tax", label: "Tax", count: 11 },
    { id: "funds_etfs", label: "Funds & ETFs", count: 11 },
  ],
  levels: ["beginner", "intermediate", "advanced"],
};

export const ARTICLE: Article = {
  ...WASH_SALE,
  body_md: "# The Wash Sale Rule\n\nA wash sale happens when **you sell at a loss**.",
  related: [{ ...WASH_SALE, id: "tax-loss-harvesting", title: "Tax-Loss Harvesting", level: "advanced", reading_minutes: 3 }],
};
