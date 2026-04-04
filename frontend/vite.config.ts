import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import UnoCSS from "unocss/vite";
import path from "path";

export default defineConfig({
  plugins: [
    vue(),
    UnoCSS(),
  ],
  server: {
    host: "127.0.0.1",
    port: 7000,
    strictPort: false,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:9090",
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
});
