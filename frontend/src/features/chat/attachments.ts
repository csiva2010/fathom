import type { ImageAttachment } from "@/api/types";

/** Matches the backend default (workflow.max_image_bytes); the server checks again. */
export const MAX_IMAGE_BYTES = 5_000_000;
export const IMAGE_TYPES: readonly ImageAttachment["media_type"][] = ["image/png", "image/jpeg", "image/webp"];
/** What the server asks when a screenshot is sent without text. */
export const SCREENSHOT_QUESTION = "Analyze the portfolio in this screenshot.";

/** A screenshot ready to send: base64 for the API, a data URL for the preview. */
export interface Attachment {
  name: string;
  mediaType: ImageAttachment["media_type"];
  data: string;
  previewUrl: string;
}

const isImageType = (type: string): type is ImageAttachment["media_type"] =>
  (IMAGE_TYPES as readonly string[]).includes(type);

/** Read a pasted, dropped or picked file; rejects with a message to show the user. */
export function readImage(file: File): Promise<Attachment> {
  if (!isImageType(file.type)) return Promise.reject(new Error("Attach a PNG, JPEG or WebP image."));
  if (file.size > MAX_IMAGE_BYTES) {
    return Promise.reject(new Error(`Images must be under ${MAX_IMAGE_BYTES / 1_000_000} MB.`));
  }
  const mediaType = file.type;
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("That image couldn't be read. Try another file."));
    reader.onload = () => {
      const url = String(reader.result);
      resolve({ name: file.name || "screenshot", mediaType, data: url.slice(url.indexOf(",") + 1), previewUrl: url });
    };
    reader.readAsDataURL(file);
  });
}

/** The first image among pasted or dropped items, if any. */
export function imageFrom(items: DataTransferItemList | undefined, files: FileList | undefined): File | null {
  for (const item of Array.from(items ?? [])) {
    if (item.kind === "file" && item.type.startsWith("image/")) return item.getAsFile();
  }
  return Array.from(files ?? []).find((f) => f.type.startsWith("image/")) ?? null;
}

export const toImageAttachment = (a: Attachment): ImageAttachment => ({ media_type: a.mediaType, data: a.data });
