import { useSearchParams } from "react-router-dom";

import { EmptyState } from "@/components/feedback/EmptyState";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { chipClass, INPUT_CLASS } from "@/components/ui/styles";
import { useDebounced } from "@/lib/hooks/useDebounced";

import { useArticles } from "../hooks/useLearn";
import { ArticleCard } from "./ArticleCard";

/** Browse and search articles by category and level (KB-08). Filters live in the URL. */
export function ArticleBrowser() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const category = params.get("category") ?? "";
  const level = params.get("level") ?? "";
  const debouncedQ = useDebounced(q.trim());
  const articles = useArticles({ q: debouncedQ, category, level });

  const update = (key: string, value: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3">
        <div className="min-w-56 flex-1">
          <label htmlFor="article-search" className="sr-only">
            Search articles
          </label>
          <input
            id="article-search"
            type="search"
            value={q}
            onChange={(e) => update("q", e.target.value)}
            placeholder="Search articles, e.g. index funds or wash sale"
            className={INPUT_CLASS}
          />
        </div>
        <div>
          <label htmlFor="article-level" className="sr-only">
            Level
          </label>
          <select id="article-level" value={level} onChange={(e) => update("level", e.target.value)} className={INPUT_CLASS}>
            <option value="">All levels</option>
            {(articles.data?.levels ?? ["beginner", "intermediate", "advanced"]).map((l) => (
              <option key={l} value={l}>
                {l.charAt(0).toUpperCase() + l.slice(1)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {articles.data && (
        <div role="group" aria-label="Categories" className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
          <button type="button" className={chipClass(!category)} onClick={() => update("category", "")} aria-pressed={!category}>
            All topics
          </button>
          {articles.data.categories.map((c) => (
            <button
              key={c.id}
              type="button"
              className={chipClass(category === c.id)}
              onClick={() => update("category", category === c.id ? "" : c.id)}
              aria-pressed={category === c.id}
            >
              {c.label} <span className="opacity-70">{c.count}</span>
            </button>
          ))}
        </div>
      )}

      {articles.isPending && <LoadingState label="Loading articles" />}
      {articles.isError && <ErrorState title="Couldn't load articles" error={articles.error} onRetry={() => void articles.refetch()} />}
      {articles.data && articles.data.articles.length === 0 && (
        <EmptyState title="No articles match">Try a different word, or clear the filters.</EmptyState>
      )}
      {articles.data && articles.data.articles.length > 0 && (
        <>
          <p className="text-xs text-slate-500 dark:text-slate-400" aria-live="polite">
            {articles.data.articles.length} article{articles.data.articles.length === 1 ? "" : "s"}
          </p>
          <ul className="grid gap-3 sm:grid-cols-2">
            {articles.data.articles.map((a) => (
              <li key={a.id}>
                <ArticleCard article={a} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
