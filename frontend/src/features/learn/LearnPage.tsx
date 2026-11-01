import { useSearchParams } from "react-router-dom";

import { PageHeader } from "@/components/layout/PageHeader";
import { chipClass } from "@/components/ui/styles";

import { ArticleBrowser } from "./components/ArticleBrowser";
import { GlossaryBrowser } from "./components/GlossaryBrowser";

/** The Learn tab: articles by topic and level, plus the glossary (KB-08). */
export function LearnPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "glossary" ? "glossary" : "articles";

  return (
    <section>
      <PageHeader title="Learn" description="Short, sourced explainers on investing, saving and taxes, at your level." />
      <div role="tablist" aria-label="Learn sections" className="mb-4 flex gap-2">
        {(["articles", "glossary"] as const).map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={tab === t}
            className={chipClass(tab === t)}
            onClick={() => setParams(t === "glossary" ? { tab: t } : {})}
          >
            {t === "articles" ? "Articles" : "Glossary"}
          </button>
        ))}
      </div>
      <div role="tabpanel">{tab === "articles" ? <ArticleBrowser /> : <GlossaryBrowser />}</div>
    </section>
  );
}
