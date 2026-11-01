import type { Components } from "react-markdown";

import { Markdown } from "@/components/ui/Markdown";

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
      <a href={href} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    );
  },
};

/** Answer text, with [n] markers linked to the matching source card (CH-04). */
export function MessageMarkdown({ content, messageId, citationCount }: { content: string; messageId: string; citationCount: number }) {
  return <Markdown components={components}>{linkCitations(content, messageId, citationCount)}</Markdown>;
}
