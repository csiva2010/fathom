/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  // Non-VITE_ variables are only visible here, never in the browser bundle.
  const env = loadEnv(mode, process.cwd(), "");
  const webPort = Number(env.WEB_PORT || 5173);
  const apiTarget = env.API_PROXY_TARGET || `http://localhost:${env.API_PORT || 8000}`;

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
    },
    server: {
      port: webPort,
      // Fail instead of silently moving: the backend's URLs and the Google redirect URI
      // are derived from WEB_PORT, so a different port would break sign-in.
      strictPort: true,
      // Same-origin /api keeps the HttpOnly session cookie and SSE simple.
      proxy: { "/api": { target: apiTarget, changeOrigin: false } },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      css: false,
      coverage: {
        provider: "v8",
        include: ["src/**/*.{ts,tsx}"],
        exclude: ["src/api/generated/**", "src/test/**", "src/main.tsx", "**/*.test.{ts,tsx}", "**/*.d.ts"],
        reporter: ["text-summary", "text"],
        // Same bar as the backend (NF-T01).
        thresholds: { statements: 90, lines: 90, functions: 85, branches: 80 },
      },
    },
  };
});
