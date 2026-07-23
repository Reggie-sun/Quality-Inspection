import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";


export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: ["qa.srj666.com"],
    proxy: {
      "/api": {
        target: "http://api:8000",
        changeOrigin: false,
      },
    },
  },
});
