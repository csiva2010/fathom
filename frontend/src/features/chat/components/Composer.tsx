import {
  useRef,
  useState,
  type ChangeEvent,
  type ClipboardEvent,
  type DragEvent,
  type FormEvent,
  type KeyboardEvent,
} from "react";

import { Button } from "@/components/ui/Button";

import { IMAGE_TYPES, imageFrom, readImage, type Attachment } from "../attachments";

export const MAX_MESSAGE_CHARS = 4000;

interface ComposerProps {
  onSend: (text: string, image?: Attachment) => void;
  onStop: () => void;
  streaming: boolean;
  /** Text to start with, e.g. a question handed over from the Learn tab. */
  initialText?: string;
}

/**
 * Enter sends, Shift+Enter adds a line. A portfolio screenshot can be pasted, dropped or
 * picked from disk (CH-09); it is sent with the next message and never stored.
 */
export function Composer({ onSend, onStop, streaming, initialText = "" }: ComposerProps) {
  const [text, setText] = useState(initialText);
  const [image, setImage] = useState<Attachment | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const tooLong = text.length > MAX_MESSAGE_CHARS;
  const canSend = (text.trim().length > 0 || image !== null) && !tooLong;

  const attach = (file: File | null) => {
    if (!file) return;
    setImageError(null);
    readImage(file).then(setImage, (error: Error) => setImageError(error.message));
  };

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (streaming || !canSend) return;
    onSend(text, image ?? undefined);
    setText("");
    setImage(null);
    setImageError(null);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) submit(event);
  };
  const onPaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const file = imageFrom(event.clipboardData.items, event.clipboardData.files);
    if (file) {
      event.preventDefault();
      attach(file);
    }
  };
  const onDrop = (event: DragEvent<HTMLFormElement>) => {
    setDragging(false);
    const file = imageFrom(event.dataTransfer.items, event.dataTransfer.files);
    if (file) {
      event.preventDefault();
      attach(file);
    }
  };
  const onPick = (event: ChangeEvent<HTMLInputElement>) => {
    attach(event.target.files?.[0] ?? null);
    event.target.value = ""; // picking the same file again still fires
  };

  return (
    <form
      onSubmit={submit}
      onDragOver={(e) => {
        if (Array.from(e.dataTransfer.types).includes("Files")) {
          e.preventDefault();
          setDragging(true);
        }
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className="space-y-1"
    >
      <div
        className={`rounded-xl border bg-white p-2 focus-within:border-emerald-600 dark:bg-slate-900 ${
          dragging ? "border-emerald-600 ring-2 ring-emerald-600/30" : "border-slate-300 dark:border-slate-600"
        }`}
      >
        {image && (
          <div className="mb-2 flex items-center gap-3 px-2">
            <img src={image.previewUrl} alt="Attached screenshot" className="h-16 w-auto rounded border border-slate-200 dark:border-slate-700" />
            <div className="min-w-0 text-xs text-slate-600 dark:text-slate-300">
              <p className="truncate font-medium">{image.name}</p>
              <p>Holdings will be read from this image; it isn&apos;t stored.</p>
            </div>
            <button
              type="button"
              onClick={() => setImage(null)}
              aria-label="Remove screenshot"
              className="ml-auto rounded px-2 py-1 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-100"
            >
              ✕
            </button>
          </div>
        )}
        <div className="flex items-end gap-2">
          <input
            ref={fileInput}
            type="file"
            accept={IMAGE_TYPES.join(",")}
            onChange={onPick}
            className="hidden"
            data-testid="screenshot-input"
          />
          <Button
            variant="secondary"
            onClick={() => fileInput.current?.click()}
            disabled={streaming}
            aria-label="Attach a portfolio screenshot"
            title="Attach a portfolio screenshot (or paste / drop one)"
          >
            Image
          </Button>
          <label htmlFor="chat-input" className="sr-only">
            Ask a question
          </label>
          <textarea
            id="chat-input"
            rows={2}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKeyDown}
            onPaste={onPaste}
            placeholder={
              image
                ? "Add a question about these holdings, or just send…"
                : "Ask about a concept, a ticker, your portfolio or a goal, or paste a portfolio screenshot…"
            }
            className="max-h-40 min-h-10 flex-1 resize-y bg-transparent px-2 py-1 text-sm outline-none placeholder:text-slate-400"
          />
          {streaming ? (
            <Button variant="secondary" onClick={onStop}>
              Stop
            </Button>
          ) : (
            <Button type="submit" disabled={!canSend}>
              Send
            </Button>
          )}
        </div>
      </div>
      {tooLong && (
        <p role="alert" className="text-xs text-rose-700 dark:text-rose-300">
          Keep messages under {MAX_MESSAGE_CHARS} characters ({text.length} now).
        </p>
      )}
      {imageError && (
        <p role="alert" className="text-xs text-rose-700 dark:text-rose-300">
          {imageError}
        </p>
      )}
    </form>
  );
}
