import { Link } from "react-router-dom";

import type { ArticleSummary } from "@/api/types";

import { LevelBadge } from "./LevelBadge";

/** One article in a list: topic, level, reading time, title and summary. */
export function ArticleCard({ article }: { article: ArticleSummary }) {
  return (
    <Link
      to={`/learn/${article.id}`}
      className="block h-full rounded-xl border border-slate-200 p-4 hover:border-emerald-600 dark:border-slate-700 dark:hover:border-emerald-400"
    >
      <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
        <span>{article.category_label}</span>
        <LevelBadge level={article.level} />
        <span>{article.reading_minutes} min read</span>
      </div>
      <h3 className="font-semibold">{article.title}</h3>
      <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{article.summary}</p>
    </Link>
  );
}
