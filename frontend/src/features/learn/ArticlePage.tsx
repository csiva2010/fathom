import { Link, useParams } from "react-router-dom";

import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { Markdown } from "@/components/ui/Markdown";

import { askAbout } from "./ask";
import { ArticleCard } from "./components/ArticleCard";
import { LevelBadge } from "./components/LevelBadge";
import { useArticle } from "./hooks/useLearn";

/** One article, with its source and review date (KB-03), and what to read next. */
export function ArticlePage() {
  const { articleId = "" } = useParams();
  const article = useArticle(articleId);

  return (
    <article className="mx-auto max-w-3xl space-y-4">
      <Link to="/learn" className="text-sm text-emerald-700 hover:underline dark:text-emerald-300">
        ← All articles
      </Link>
      {article.isPending && <LoadingState label="Loading article" />}
      {article.isError && <ErrorState title="Couldn't load this article" error={article.error} onRetry={() => void article.refetch()} />}
      {article.data && (
        <>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
            <Link to={`/learn?category=${article.data.category}`} className="hover:underline">
              {article.data.category_label}
            </Link>
            <LevelBadge level={article.data.level} />
            <span>{article.data.reading_minutes} min read</span>
            <Link
              to={`/chat?ask=${encodeURIComponent(askAbout(article.data.title))}`}
              className="ml-auto rounded-full border border-emerald-700 px-3 py-1 font-medium text-emerald-800 hover:bg-emerald-50 dark:border-emerald-400 dark:text-emerald-200 dark:hover:bg-emerald-950"
            >
              Ask Fathom about this
            </Link>
          </div>
          <Markdown>{article.data.body_md}</Markdown>
          <footer className="space-y-2 border-t border-slate-200 pt-3 text-xs text-slate-500 dark:border-slate-700 dark:text-slate-400">
            <p>
              Source:{" "}
              <a href={article.data.source_url} target="_blank" rel="noopener noreferrer" className="text-emerald-700 underline dark:text-emerald-300">
                {article.data.source_name}
              </a>{" "}
              · Reviewed {/* A date-only value is UTC midnight; format it in UTC so it doesn't shift a day. */}
              {new Date(article.data.last_reviewed).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" })}
            </p>
            {article.data.tags.length > 0 && (
              <p className="flex flex-wrap gap-1.5">
                {article.data.tags.map((tag) => (
                  <Link key={tag} to={`/learn?q=${encodeURIComponent(tag)}`} className="rounded-full bg-slate-100 px-2 py-0.5 hover:bg-slate-200 dark:bg-slate-800">
                    {tag}
                  </Link>
                ))}
              </p>
            )}
          </footer>
          {(article.data.related ?? []).length > 0 && (
            <section aria-labelledby="keep-learning" className="space-y-2 pt-2">
              <h2 id="keep-learning" className="text-sm font-semibold">
                Keep learning
              </h2>
              <ul className="grid gap-3 sm:grid-cols-3">
                {(article.data.related ?? []).map((a) => (
                  <li key={a.id}>
                    <ArticleCard article={a} />
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </article>
  );
}
