import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const apiProxyTarget = process.env.QI_API_PROXY_TARGET ?? "http://api:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: ["qa.srj666.com"],
    proxy: {
      "/api": {
        target: apiProxyTarget,
        changeOrigin: false,
      },
    },
  },
});
