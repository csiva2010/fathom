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
