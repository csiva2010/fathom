/** Full-page navigation (used for the OAuth redirect). Kept separate so tests can spy on it. */
export function redirectTo(url: string): void {
  window.location.assign(url);
}
