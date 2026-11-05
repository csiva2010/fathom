import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Composer } from "../components/Composer";
import { appendSpoken, type SpeechRecognitionLike } from "./useSpeechInput";

/** Stands in for the browser's recognizer; `hear` and `fail` play the browser's events. */
class FakeRecognition implements SpeechRecognitionLike {
  static last: FakeRecognition;
  continuous = false;
  interimResults = false;
  lang = "";
  onresult: SpeechRecognitionLike["onresult"] = null;
  onerror: SpeechRecognitionLike["onerror"] = null;
  onend: SpeechRecognitionLike["onend"] = null;
  start = vi.fn();
  stop = vi.fn(() => this.end());
  abort = vi.fn(() => this.end());

  constructor() {
    FakeRecognition.last = this;
  }
  hear(...parts: string[]) {
    act(() => this.onresult?.({ results: parts.map((transcript) => [{ transcript }]) }));
  }
  fail(error: string) {
    act(() => {
      this.onerror?.({ error });
      this.onend?.();
    });
  }
  private end() {
    this.onend?.();
  }
}

function setup(props: Partial<Parameters<typeof Composer>[0]> = {}) {
  const onSend = vi.fn();
  const view = render(<Composer onSend={onSend} onStop={vi.fn()} streaming={false} {...props} />);
  return { onSend, view, box: screen.getByLabelText("Ask a question") };
}

const mic = () => screen.getByRole("button", { name: "Speak your question" });
const stopMic = () => screen.getByRole("button", { name: "Stop voice input" });

describe("voice input", () => {
  beforeEach(() => {
    vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
  });

  it("is hidden when the browser has no speech recognition", () => {
    vi.unstubAllGlobals();
    setup();
    expect(screen.queryByRole("button", { name: "Speak your question" })).not.toBeInTheDocument();
  });

  it("appends what is heard to the typed text, then sends on Send", async () => {
    const { onSend, box } = setup();
    await userEvent.type(box, "Explain");
    await userEvent.click(mic());

    const rec = FakeRecognition.last;
    expect(rec.start).toHaveBeenCalled();
    expect(rec.continuous).toBe(true);
    expect(rec.interimResults).toBe(true);
    expect(rec.lang).not.toBe("");
    expect(stopMic()).toHaveAttribute("aria-pressed", "true");
    expect(box).toHaveAttribute("readonly");

    rec.hear("the wash"); // interim words
    expect(box).toHaveValue("Explain the wash");
    rec.hear("the wash sale", " rule");
    expect(box).toHaveValue("Explain the wash sale rule");

    await userEvent.click(stopMic());
    expect(rec.stop).toHaveBeenCalled();
    expect(mic()).toHaveAttribute("aria-pressed", "false");
    expect(box).not.toHaveAttribute("readonly");

    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onSend).toHaveBeenCalledWith("Explain the wash sale rule", undefined);
  });

  it("stops listening when the message is sent and ignores late words", async () => {
    const { onSend, box } = setup();
    await userEvent.click(mic());
    const rec = FakeRecognition.last;
    rec.hear("what is a bond");
    await userEvent.type(box, "{Enter}");

    expect(onSend).toHaveBeenCalledWith("what is a bond", undefined);
    expect(rec.abort).toHaveBeenCalled();
    rec.hear("late words");
    expect(box).toHaveValue("");
  });

  it("explains a blocked microphone and stays quiet when aborted", async () => {
    setup();
    await userEvent.click(mic());
    FakeRecognition.last.fail("not-allowed");
    expect(screen.getByRole("alert")).toHaveTextContent("Microphone access is blocked");

    await userEvent.click(mic()); // trying again clears the message
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    FakeRecognition.last.fail("aborted");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    await userEvent.click(mic());
    FakeRecognition.last.fail("something-new");
    expect(screen.getByRole("alert")).toHaveTextContent("Voice input stopped unexpectedly");
  });

  it("is disabled while an answer streams and stops on unmount", async () => {
    const { view } = setup();
    await userEvent.click(mic());
    const rec = FakeRecognition.last;
    view.unmount();
    expect(rec.abort).toHaveBeenCalled();

    setup({ streaming: true });
    expect(mic()).toBeDisabled();
  });
});

describe("appendSpoken", () => {
  it("joins typed and spoken text with one space", () => {
    expect(appendSpoken("", " hello ")).toBe("hello");
    expect(appendSpoken("Explain  ", "beta")).toBe("Explain beta");
    expect(appendSpoken("Explain", "  ")).toBe("Explain");
    expect(appendSpoken("", "")).toBe("");
  });
});
