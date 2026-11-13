import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self' 'unsafe-inline'",
  "connect-src 'self' http://127.0.0.1:* ws://127.0.0.1:*",
  "frame-src https://*.tradingview.com",
  "img-src 'self' data:",
  "font-src 'self' data:",
].join("; ");

// Production builds get a strict content security policy. The dev server is
// left alone because Vite's hot reload needs an inline script.
const csp: Plugin = {
  name: "qt-csp",
  apply: "build",
  transformIndexHtml: (html) =>
    html.replace(
      "<title>",
      `<meta http-equiv="Content-Security-Policy" content="${CSP}" />\n    <title>`,
    ),
};

export default defineConfig({
  base: "./", // relative asset paths so Electron can load the build from disk
  plugins: [react(), tailwindcss(), csp],
  server: { port: 5173, strictPort: true },
});
