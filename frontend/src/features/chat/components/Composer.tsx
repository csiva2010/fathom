import { useState, type FormEvent, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/Button";

export const MAX_MESSAGE_CHARS = 4000;

interface ComposerProps {
  onSend: (text: string) => void;
  onStop: () => void;
  streaming: boolean;
}

/** Enter sends, Shift+Enter adds a line. */
export function Composer({ onSend, onStop, streaming }: ComposerProps) {
  const [text, setText] = useState("");
  const tooLong = text.length > MAX_MESSAGE_CHARS;

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (streaming || !text.trim() || tooLong) return;
    onSend(text);
    setText("");
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) submit(event);
  };

  return (
    <form onSubmit={submit} className="space-y-1">
      <div className="flex items-end gap-2 rounded-xl border border-slate-300 bg-white p-2 focus-within:border-emerald-600 dark:border-slate-600 dark:bg-slate-900">
        <label htmlFor="chat-input" className="sr-only">
          Ask a question
        </label>
        <textarea
          id="chat-input"
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about a concept, a ticker, your portfolio or a goal…"
          className="max-h-40 min-h-10 flex-1 resize-y bg-transparent px-2 py-1 text-sm outline-none placeholder:text-slate-400"
        />
        {streaming ? (
          <Button variant="secondary" onClick={onStop}>
            Stop
          </Button>
        ) : (
          <Button type="submit" disabled={!text.trim() || tooLong}>
            Send
          </Button>
        )}
      </div>
      {tooLong && (
        <p role="alert" className="text-xs text-rose-700 dark:text-rose-300">
          Keep messages under {MAX_MESSAGE_CHARS} characters ({text.length} now).
        </p>
      )}
    </form>
  );
}
