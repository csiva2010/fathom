import { createEvent, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { imageFrom, MAX_IMAGE_BYTES, readImage } from "../attachments";
import { Composer } from "./Composer";

const png = (name = "holdings.png") => new File([new Uint8Array([137, 80, 78, 71])], name, { type: "image/png" });

/** A DataTransfer-like object: jsdom has none, and the composer only reads these fields. */
function transfer(files: File[], types = ["Files"]) {
  return {
    types,
    files,
    items: files.map((f) => ({ kind: "file", type: f.type, getAsFile: () => f })),
  };
}

function setup(props: Partial<Parameters<typeof Composer>[0]> = {}) {
  const onSend = vi.fn();
  const onStop = vi.fn();
  render(<Composer onSend={onSend} onStop={onStop} streaming={false} {...props} />);
  return { onSend, onStop, box: screen.getByLabelText("Ask a question") };
}

describe("Composer", () => {
  it("starts with handed-over text and sends on Enter, not Shift+Enter", async () => {
    const { onSend, box } = setup({ initialText: "What is a REIT?" });
    expect(box).toHaveValue("What is a REIT?");
    await userEvent.type(box, "{Shift>}{Enter}{/Shift}");
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.type(box, "{Enter}");
    expect(onSend).toHaveBeenCalledWith("What is a REIT?\n", undefined);
    expect(box).toHaveValue("");
  });

  it("attaches a pasted image and can remove it", async () => {
    const { onSend, box } = setup();
    const paste = createEvent.paste(box);
    Object.assign(paste, { clipboardData: transfer([png()]) });
    fireEvent(box, paste);
    expect(await screen.findByAltText("Attached screenshot")).toBeInTheDocument();
    expect(screen.getByText("holdings.png")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Remove screenshot" }));
    expect(screen.queryByAltText("Attached screenshot")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(onSend).not.toHaveBeenCalled();
  });

  it("accepts a dropped image and highlights while dragging files", async () => {
    const { onSend } = setup();
    const form = screen.getByLabelText("Ask a question").closest("form") as HTMLFormElement;
    fireEvent.dragOver(form, { dataTransfer: transfer([], ["text/plain"]) }); // not files: ignored
    expect(form.firstElementChild).not.toHaveClass("ring-2");
    fireEvent.dragOver(form, { dataTransfer: transfer([]) });
    expect(form.firstElementChild).toHaveClass("ring-2");
    fireEvent.dragLeave(form);
    expect(form.firstElementChild).not.toHaveClass("ring-2");

    fireEvent.drop(form, { dataTransfer: transfer([png("drop.png")]) });
    expect(await screen.findByText("drop.png")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onSend).toHaveBeenCalledWith("", expect.objectContaining({ name: "drop.png", mediaType: "image/png" }));
  });

  it("shows why an image was refused", async () => {
    setup();
    await userEvent.upload(screen.getByTestId("screenshot-input"), new File(["x"], "notes.txt", { type: "text/plain" }), {
      applyAccept: false,
    });
    expect(await screen.findByRole("alert")).toHaveTextContent("Attach a PNG, JPEG or WebP image.");
  });

  it("offers Stop while an answer streams", async () => {
    const { onStop, onSend, box } = setup({ streaming: true });
    await userEvent.type(box, "Next question{Enter}");
    expect(onSend).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(onStop).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Attach a portfolio screenshot" })).toBeDisabled();
  });
});

describe("attachments", () => {
  it("rejects oversized images and finds images among plain files", async () => {
    const big = new File([new Uint8Array(MAX_IMAGE_BYTES + 1)], "big.png", { type: "image/png" });
    await expect(readImage(big)).rejects.toThrow("Images must be under 5 MB.");
    const files = [new File(["a"], "a.txt", { type: "text/plain" }), png()] as unknown as FileList;
    expect(imageFrom(undefined, files)?.name).toBe("holdings.png");
    expect(imageFrom(undefined, undefined)).toBeNull();
  });

  it("reports an unreadable file", async () => {
    const original = globalThis.FileReader;
    class FailingReader {
      onerror: (() => void) | null = null;
      onload: (() => void) | null = null;
      readAsDataURL() {
        queueMicrotask(() => this.onerror?.());
      }
    }
    globalThis.FileReader = FailingReader as unknown as typeof FileReader;
    try {
      await expect(readImage(png())).rejects.toThrow("couldn't be read");
    } finally {
      globalThis.FileReader = original;
    }
    await waitFor(() => expect(globalThis.FileReader).toBe(original));
  });
});
