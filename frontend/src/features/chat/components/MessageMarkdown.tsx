import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { CITE_PREFIX, linkCitations } from "../citations";

const components: Components = {
  a({ href, children }) {
    if (href?.startsWith(CITE_PREFIX)) {
      return (
        <sup>
          <a
            href={href}
            className="rounded px-0.5 text-[0.7rem] font-semibold text-emerald-700 no-underline hover:bg-emerald-50 dark:text-emerald-300 dark:hover:bg-emerald-900/40"
            aria-label={`Source ${String(children)}`}
          >
            [{children}]
          </a>
        </sup>
      );
    }
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className="text-emerald-700 underline dark:text-emerald-300">
        {children}
      </a>
    );
  },
};

/**
 * Answer text as Markdown. Raw HTML is never rendered (react-markdown's default), so text
 * quoted from news or sources can't inject markup.
 */
export function MessageMarkdown({ content, messageId, citationCount }: { content: string; messageId: string; citationCount: number }) {
  return (
    <div className="prose-chat space-y-3 text-sm leading-relaxed [&_blockquote]:border-l-2 [&_blockquote]:border-amber-400 [&_blockquote]:pl-3 [&_blockquote]:text-slate-600 dark:[&_blockquote]:text-slate-300 [&_h3]:font-semibold [&_li]:ml-5 [&_ol]:list-decimal [&_table]:text-xs [&_td]:border [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:px-2 [&_th]:py-1 [&_ul]:list-disc">
      <Markdown remarkPlugins={[remarkGfm]} components={components}>
        {linkCitations(content, messageId, citationCount)}
      </Markdown>
    </div>
  );
}
