// Cross-platform dev launcher: starts the Vite dev server, then Electron
// (which starts the Python engine itself). Closing the app stops everything.
// Usage: node scripts/dev.mjs [--built]   --built loads apps/web/dist instead
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(import.meta.url);
const electron = require("electron"); // path to the Electron binary
const viteBin = join(dirname(require.resolve("vite/package.json")), "bin", "vite.js");
const built = process.argv.includes("--built");
const WEB_URL = "http://localhost:5173";

const children = [];
function start(cmd, args, opts) {
  const child = spawn(cmd, args, { stdio: "inherit", ...opts });
  children.push(child);
  return child;
}
function shutdown(code = 0) {
  for (const c of children) if (!c.killed) c.kill();
  process.exit(code);
}
process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));

async function waitFor(url, ms = 30_000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    try {
      if ((await fetch(url)).ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

const env = { ...process.env };
if (!built) {
  start(process.execPath, [viteBin], { cwd: join(root, "apps", "web") });
  await waitFor(WEB_URL).catch((e) => {
    console.error(e.message);
    shutdown(1);
  });
  env.QT_WEB_URL = WEB_URL;
}
const app = start(electron, [join(root, "apps", "desktop")], { cwd: root, env });
app.on("exit", (code) => shutdown(code ?? 0));
