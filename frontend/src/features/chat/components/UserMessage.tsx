export function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-emerald-700 px-4 py-2 text-sm text-white dark:bg-emerald-600">
        {content}
      </p>
    </div>
  );
}
