// Cross-platform (macOS + Windows) launcher for the Python engine.
// Usage: node scripts/engine.mjs <setup|dev|test>
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const engine = join(root, "engine");
const win = process.platform === "win32";
const venvPy = join(engine, ".venv", win ? "Scripts" : "bin", win ? "python.exe" : "python");

function run(cmd, args) {
  const r = spawnSync(cmd, args, { cwd: engine, stdio: "inherit" });
  if (r.error) {
    console.error(`Could not run ${cmd}: ${r.error.message}`);
    process.exit(1);
  }
  if (r.status !== 0) process.exit(r.status ?? 1);
}

function needVenv() {
  if (!existsSync(venvPy)) {
    console.error("Engine is not set up yet. Run: npm run engine:setup");
    process.exit(1);
  }
}

const cmd = process.argv[2];
if (cmd === "setup") {
  if (!existsSync(venvPy)) {
    if (win) run("py", ["-3", "-m", "venv", ".venv"]);
    else run("python3", ["-m", "venv", ".venv"]);
  }
  run(venvPy, ["-m", "pip", "install", "--upgrade", "pip"]);
  run(venvPy, ["-m", "pip", "install", "-e", ".[dev]"]);
} else if (cmd === "dev") {
  needVenv();
  run(venvPy, ["-m", "app.server"]);
} else if (cmd === "test") {
  needVenv();
  run(venvPy, ["-m", "pytest", "-q", ...process.argv.slice(3)]);
} else {
  console.error("Usage: node scripts/engine.mjs <setup|dev|test>");
  process.exit(1);
}
