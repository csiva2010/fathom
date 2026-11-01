import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const STYLES =
  "space-y-3 text-sm leading-relaxed [&_a]:text-emerald-700 [&_a]:underline dark:[&_a]:text-emerald-300 [&_blockquote]:border-l-2 [&_blockquote]:border-amber-400 [&_blockquote]:pl-3 [&_blockquote]:text-slate-600 dark:[&_blockquote]:text-slate-300 [&_h1]:text-xl [&_h1]:font-semibold [&_h2]:mt-5 [&_h2]:text-base [&_h2]:font-semibold [&_h3]:font-semibold [&_li]:ml-5 [&_ol]:list-decimal [&_table]:text-xs [&_td]:border [&_td]:px-2 [&_td]:py-1 [&_th]:border [&_th]:px-2 [&_th]:py-1 [&_ul]:list-disc";

const external: Components = {
  a({ href, children }) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    );
  },
};

/**
 * GitHub-flavored Markdown. Raw HTML is never rendered (react-markdown's default), so
 * text from articles, news or the model can't inject markup.
 */
export function Markdown({ children, components }: { children: string; components?: Components }) {
  return (
    <div className={STYLES}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ ...external, ...components }}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
