interface UserMessageProps {
  content: string;
  /** Preview of a screenshot being sent now (kept in memory only). */
  imageUrl?: string;
  /** A past message that came with a screenshot; the image itself isn't stored. */
  hasImage?: boolean;
}

export function UserMessage({ content, imageUrl, hasImage = false }: UserMessageProps) {
  return (
    <div className="flex flex-col items-end gap-1">
      {imageUrl ? (
        <img
          src={imageUrl}
          alt="Portfolio screenshot you sent"
          className="max-h-48 max-w-[60%] rounded-xl border border-slate-200 dark:border-slate-700"
        />
      ) : (
        hasImage && (
          <span className="rounded-full bg-slate-100 px-3 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            Screenshot attached (not stored)
          </span>
        )
      )}
      <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-emerald-700 px-4 py-2 text-sm text-white dark:bg-emerald-600">
        {content}
      </p>
    </div>
  );
}
