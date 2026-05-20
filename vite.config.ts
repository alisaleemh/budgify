import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  root: "web_src",
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "web_src/src"),
    },
  },
  build: {
    outDir: path.resolve(__dirname, "transaction_tracker/web_ui"),
    emptyOutDir: true,
  },
});
