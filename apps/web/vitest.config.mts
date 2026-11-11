import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "."),
      "@intervue/types": path.resolve(import.meta.dirname, "../../packages/types/src/index.ts"),
      "@intervue/config": path.resolve(import.meta.dirname, "../../packages/config/src/index.ts"),
    },
  },
  test: {
    environment: "jsdom",
    include: ["tests/unit/**/*.test.{ts,tsx}"],
  },
});
