import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    outDir: "../agent_framework_devui/ui",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // Minimize to just 2 files: main app + CSS
        manualChunks: undefined,
        // Ensure everything goes into a single JS file
        inlineDynamicImports: true,
      },
    },
  },
  // Ensure proper tree-shaking
  optimizeDeps: {
    include: ["lucide-react", "@xyflow/react"],
  },
  // Enable aggressive tree-shaking
  esbuild: {
    treeShaking: true,
  },
});
