import { apiFetch } from "../client";
import type { Article, ArticleList, GlossaryList } from "../types";

export interface ArticleFilters {
  q?: string;
  category?: string;
  level?: string;
}

export function listArticles(filters: ArticleFilters): Promise<ArticleList> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value);
  const query = params.toString();
  return apiFetch<ArticleList>(`/kb/articles${query ? `?${query}` : ""}`);
}

export function getArticle(id: string): Promise<Article> {
  return apiFetch<Article>(`/kb/articles/${encodeURIComponent(id)}`);
}

export function searchGlossary(q: string): Promise<GlossaryList> {
  return apiFetch<GlossaryList>(`/kb/glossary?${new URLSearchParams({ q, limit: "300" })}`);
}
