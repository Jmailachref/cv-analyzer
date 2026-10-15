import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Served by the API under /app. `npm run dev` proxies the API (CVA_API, default the compose one).
export default defineConfig({
  base: "/app/",
  plugins: [react(), tailwindcss()],
  // pdf.js alone is about 400 kB.
  build: { chunkSizeWarningLimit: 1000 },
  server: {
    proxy: { "/v1": process.env.CVA_API ?? "http://localhost:8100" },
  },
});
