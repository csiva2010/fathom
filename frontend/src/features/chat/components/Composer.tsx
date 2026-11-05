import {
  useCallback,
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
import { appendSpoken, useSpeechInput } from "../hooks/useSpeechInput";

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
 * picked from disk (CH-09); it is sent with the next message and never stored. The mic
 * button (shown where the browser supports speech recognition) fills the box from speech;
 * the text is sent only when the user presses Send.
 */
export function Composer({ onSend, onStop, streaming, initialText = "" }: ComposerProps) {
  const [text, setText] = useState(initialText);
  const [image, setImage] = useState<Attachment | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const typedBeforeSpeech = useRef("");
  const speech = useSpeechInput(
    useCallback((spoken: string) => setText(appendSpoken(typedBeforeSpeech.current, spoken)), []),
  );
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
    speech.cancel();
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
  const toggleMic = () => {
    if (speech.listening) {
      speech.stop();
    } else {
      typedBeforeSpeech.current = text;
      speech.start();
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
          {speech.supported && (
            <Button
              variant="secondary"
              onClick={toggleMic}
              disabled={streaming}
              aria-pressed={speech.listening}
              aria-label={speech.listening ? "Stop voice input" : "Speak your question"}
              title={speech.listening ? "Stop listening" : "Speak your question (your browser converts it to text)"}
              className={`px-3 ${speech.listening ? "border-rose-500 text-rose-600 dark:border-rose-400 dark:text-rose-300" : ""}`}
            >
              <MicIcon />
              {speech.listening && <span className="h-2 w-2 animate-pulse rounded-full bg-rose-500" aria-hidden="true" />}
            </Button>
          )}
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
            readOnly={speech.listening}
            placeholder={
              speech.listening
                ? "Listening… click the mic again when you're done"
                : image
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
      {speech.error && (
        <p role="alert" className="text-xs text-rose-700 dark:text-rose-300">
          {speech.error}
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

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  );
}
