import { QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";

import { App } from "@/app/App";

/** Render the whole app at a URL with a fresh, non-retrying query client. */
export function renderApp(path = "/") {
  window.history.pushState({}, "", path);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { queryClient, ...render(<App queryClient={queryClient} />) };
}
