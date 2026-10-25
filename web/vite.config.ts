/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// The API's address comes from the app's .env (API_URL), as for the backend.
// In development /api is proxied to it, without the prefix: no CORS needed.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, "..", "");
  const api = env.API_URL || "http://127.0.0.1:8010";
  return {
    plugins: [react()],
    server: {
      port: Number(env.WEB_PORT || 5173),
      proxy: {
        "/api": { target: api, changeOrigin: true, rewrite: (path: string) => path.replace(/^\/api/, "") },
      },
    },
    // Libraries in chunks of their own: cached across releases of the app.
    build: {
      rolldownOptions: {
        output: {
          codeSplitting: {
            groups: [
              { name: "mantine", test: /node_modules[\/]@mantine/ },
              { name: "vendor", test: /node_modules[\/](react|react-dom|react-router|scheduler|@tanstack)[\/]/ },
            ],
          },
        },
      },
    },
    test: { environment: "jsdom", setupFiles: "./src/test/setup.ts" },
  };
});
