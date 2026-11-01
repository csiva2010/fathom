import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { getArticle, listArticles, searchGlossary, type ArticleFilters } from "@/api/endpoints/kb";
import { queryKeys } from "@/api/queryKeys";

export function useArticles(filters: ArticleFilters) {
  return useQuery({
    queryKey: queryKeys.articles(filters),
    queryFn: () => listArticles(filters),
    placeholderData: keepPreviousData,
    staleTime: 5 * 60_000,
  });
}

export function useArticle(id: string) {
  return useQuery({ queryKey: queryKeys.article(id), queryFn: () => getArticle(id), staleTime: 5 * 60_000 });
}

export function useGlossary(q: string) {
  return useQuery({
    queryKey: queryKeys.glossary(q),
    queryFn: () => searchGlossary(q),
    placeholderData: keepPreviousData,
    staleTime: 5 * 60_000,
  });
}
