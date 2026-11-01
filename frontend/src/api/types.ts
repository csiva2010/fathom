/**
 * Friendly names for API types. The source of truth is the backend's Pydantic models,
 * exported to openapi.json and generated into ./generated/schema.d.ts (`npm run gen:api`).
 */
import type { components } from "./generated/schema";

type Schemas = components["schemas"];

export type AuthConfig = Schemas["AuthConfigOut"];
export type Me = Schemas["MeOut"];
export type Profile = Schemas["ProfileOut"];
export type ProfileUpdate = Schemas["ProfileUpdate"];
export type ExperienceLevel = Schemas["ExperienceLevel"];
export type RiskProfile = Schemas["RiskProfile"];

export type Health = Schemas["HealthResponse"];
export type ProviderHealth = Schemas["ProviderHealth"];

export type Freshness = Schemas["Freshness"];
export type DataStatus = Schemas["DataStatus"];
export type Quote = Schemas["Quote"];
export type QuotesResponse = Schemas["QuotesResponse"];
export type IndexQuote = Schemas["IndexQuote"];
export type IndexOut = Schemas["IndexOut"];
export type MarketOverview = Schemas["MarketOverviewResponse"];

export type ErrorEnvelope = Schemas["ErrorEnvelope"];

export type AgentName = Schemas["AgentName"];
export type Citation = Schemas["Citation"];
export type Artifact = Schemas["Artifact"];
export type ArtifactKind = Artifact["kind"];
export type ChatMessage = Schemas["ChatMessage"];
export type Conversation = Schemas["ConversationOut"];
export type ConversationList = Schemas["ConversationList"];
export type ConversationDetail = Schemas["ConversationDetail"];

/** One Server-Sent Event from POST /conversations/{id}/messages; `type` tells them apart. */
export type ChatEvent =
  | Schemas["RouteEvent"]
  | Schemas["AgentStartEvent"]
  | Schemas["TokenEvent"]
  | Schemas["ReplaceEvent"]
  | Schemas["ArtifactEvent"]
  | Schemas["CitationEvent"]
  | Schemas["FreshnessEvent"]
  | Schemas["DoneEvent"]
  | Schemas["ErrorEvent"];

export type RiskQuestion = Schemas["RiskQuestion"];
export type RiskAssessment = Schemas["RiskAssessmentOut"];

export type PortfolioOut = Schemas["PortfolioOut"];
export type PortfolioIn = Schemas["PortfolioIn"];
export type HoldingIn = Schemas["HoldingIn"];
export type AssetClass = NonNullable<HoldingIn["asset_class"]>;
export type PortfolioAnalysis = Schemas["PortfolioAnalysis"];
export type CsvImport = Schemas["CsvImportOut"];

export type Goal = Schemas["GoalOut"];
export type GoalIn = Schemas["GoalIn"];
export type GoalType = Goal["type"];
export type GoalProjection = Schemas["GoalProjection"];
/** Inflation is left to the backend default. */
export type ProjectionRequest = Omit<Schemas["ProjectionRequest"], "inflation_percent">;
export type ProjectionOut = Schemas["ProjectionOut"];
export type RiskProfileName = Goal["risk_profile"];

export type ArticleSummary = Schemas["ArticleSummary"];
export type ArticleList = Schemas["ArticleList"];
export type Article = Schemas["ArticleOut"];
export type GlossaryTerm = Schemas["GlossaryTerm"];
export type GlossaryList = Schemas["GlossaryList"];

export type PriceHistoryResponse = Schemas["HistoryResponse"];
/** Mirrors the backend PriceRange enum (the history response types it as a plain string). */
export type PriceRange = "1D" | "5D" | "1M" | "3M" | "6M" | "1Y" | "5Y";
export type Movers = Schemas["MoversResponse"];
export type Sectors = Schemas["SectorsResponse"];
export type SymbolSearch = Schemas["SymbolSearchResponse"];
export type IndicatorsResponse = Schemas["IndicatorsResponse"];
export type QuoteOut = Schemas["QuoteOut"];
