export const CITE_PREFIX = "#cite-";

/** Turn "[2]" markers into links to the matching source card; unknown numbers stay text. */
export function linkCitations(text: string, messageId: string, count: number): string {
  return text.replace(/\[(\d+)\](?!\()/g, (marker, n: string) => {
    const number = Number(n);
    return number >= 1 && number <= count ? `[${n}](${CITE_PREFIX}${messageId}-${n})` : marker;
  });
}

export function citationAnchor(messageId: string, number: number): string {
  return `cite-${messageId}-${number}`;
}
