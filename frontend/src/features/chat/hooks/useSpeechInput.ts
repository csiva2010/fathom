import { useCallback, useEffect, useRef, useState } from "react";

/** The slice of the Web Speech API we use; TypeScript's DOM lib does not declare it. */
interface SpeechResultList {
  readonly length: number;
  [index: number]: { [index: number]: { transcript: string } };
}

export interface SpeechRecognitionLike {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: { results: SpeechResultList }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

type RecognitionClass = new () => SpeechRecognitionLike;

function recognitionClass(): RecognitionClass | undefined {
  const w = window as unknown as {
    SpeechRecognition?: RecognitionClass;
    webkitSpeechRecognition?: RecognitionClass;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
}

const ERRORS: Record<string, string> = {
  "not-allowed": "Microphone access is blocked. Allow it in your browser's site settings to speak a question.",
  "service-not-allowed": "Microphone access is blocked. Allow it in your browser's site settings to speak a question.",
  "audio-capture": "No microphone was found.",
  "no-speech": "Didn't catch anything. Try the mic again.",
  network: "Voice input needs an internet connection.",
};

/** Spoken words go after what was already typed, separated by one space. */
export function appendSpoken(typed: string, spoken: string): string {
  const words = spoken.trim();
  const before = typed.trimEnd();
  return before && words ? `${before} ${words}` : before || words;
}

/**
 * Speech-to-text with the browser's Web Speech API (Chrome, Edge, Safari; not Firefox).
 * `onTranscript` receives the whole transcript of the current recording, interim words
 * included, each time it changes. Nothing goes through our backend.
 */
export function useSpeechInput(onTranscript: (text: string) => void) {
  const [Recognition] = useState(recognitionClass);
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognition = useRef<SpeechRecognitionLike | null>(null);
  const callback = useRef(onTranscript);

  useEffect(() => {
    callback.current = onTranscript;
  }, [onTranscript]);

  useEffect(() => () => recognition.current?.abort(), []);

  const start = useCallback(() => {
    if (!Recognition || recognition.current) return;
    const rec = new Recognition();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = navigator.language || "en-US";
    rec.onresult = ({ results }) => {
      let text = "";
      for (let i = 0; i < results.length; i++) text += results[i]?.[0]?.transcript ?? "";
      callback.current(text);
    };
    rec.onerror = ({ error: code }) => {
      if (code !== "aborted") setError(ERRORS[code] ?? "Voice input stopped unexpectedly. Try again.");
    };
    rec.onend = () => {
      recognition.current = null;
      setListening(false);
    };
    setError(null);
    recognition.current = rec;
    setListening(true);
    rec.start();
  }, [Recognition]);

  /** Stop listening and keep what was heard. */
  const stop = useCallback(() => recognition.current?.stop(), []);

  /** Stop listening and drop any words not yet delivered (used when the message is sent). */
  const cancel = useCallback(() => {
    const rec = recognition.current;
    if (!rec) return;
    rec.onresult = null;
    rec.abort();
  }, []);

  return { supported: Recognition !== undefined, listening, error, start, stop, cancel };
}
