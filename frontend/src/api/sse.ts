/**
 * Read a `text/event-stream` body and hand each event's JSON `data` to `onData`.
 *
 * EventSource only does GET, and sending a chat message is a POST, so the stream is read
 * from the fetch response directly. Events can be split across network chunks.
 */
export async function readEventStream(
  body: ReadableStream<Uint8Array>,
  onData: (data: unknown) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const flush = (block: string) => {
    const data = block
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).replace(/^ /, ""))
      .join("\n");
    // Lines starting with ":" are keep-alive comments; blocks without data are skipped.
    if (data) onData(JSON.parse(data));
  };

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let end = buffer.indexOf("\n\n");
    while (end >= 0) {
      flush(buffer.slice(0, end));
      buffer = buffer.slice(end + 2);
      end = buffer.indexOf("\n\n");
    }
  }
  if (buffer.trim()) flush(buffer);
}
