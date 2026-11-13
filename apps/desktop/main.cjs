// Electron shell. Starts the local Python engine on a free port with a
// one-time token, waits for it, then opens the UI. The renderer gets no Node
// access: only the engine address and token, through preload.cjs.
const { app, BrowserWindow, dialog, shell } = require("electron");
const { spawn } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");

const ROOT = path.join(__dirname, "..", "..");
const WEB_URL = process.env.QT_WEB_URL; // set by scripts/dev.mjs
const WIN = process.platform === "win32";
let engine = null;
let quitting = false;

function freePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.once("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const { port } = srv.address();
      srv.close(() => resolve(port));
    });
  });
}

function engineCommand() {
  if (app.isPackaged) {
    // Phase 6: the engine ships as a PyInstaller binary next to the app.
    const bin = path.join(process.resourcesPath, "engine", WIN ? "quant-engine.exe" : "quant-engine");
    return { cmd: bin, args: [], cwd: path.dirname(bin) };
  }
  const cwd = path.join(ROOT, "engine");
  const cmd = path.join(cwd, ".venv", WIN ? "Scripts" : "bin", WIN ? "python.exe" : "python");
  return { cmd, args: ["-m", "app.server"], cwd };
}

async function startEngine() {
  const { cmd, args, cwd } = engineCommand();
  if (!fs.existsSync(cmd)) {
    throw new Error(`Engine not found at ${cmd}.\nRun "npm run engine:setup" first.`);
  }
  const port = await freePort();
  const token = crypto.randomBytes(24).toString("hex");
  engine = spawn(cmd, args, {
    cwd,
    env: { ...process.env, QT_PORT: String(port), QT_TOKEN: token, PYTHONUNBUFFERED: "1" },
    stdio: ["ignore", "inherit", "inherit"],
    windowsHide: true,
  });
  engine.on("exit", (code) => {
    engine = null;
    if (!quitting) {
      dialog.showErrorBox("Quant Terminal", `The engine stopped unexpectedly (code ${code}).`);
      app.quit();
    }
  });

  const url = `http://127.0.0.1:${port}`;
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (!engine) throw new Error("The engine exited during startup.");
    try {
      const res = await fetch(`${url}/health`);
      if (res.ok) return { url, token };
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error("The engine did not start within 30 seconds.");
}

function stopEngine() {
  if (engine) engine.kill();
  engine = null;
}

function createWindow({ url, token }) {
  const win = new BrowserWindow({
    width: 1480,
    height: 900,
    minWidth: 1000,
    minHeight: 600,
    backgroundColor: "#07080a",
    title: "Quant Terminal",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      additionalArguments: [`--qt-engine=${url}`, `--qt-token=${token}`],
    },
  });

  // The UI never navigates away; outside links open in the system browser.
  win.webContents.setWindowOpenHandler(({ url: target }) => {
    if (target.startsWith("https://")) shell.openExternal(target);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, target) => {
    if (target !== win.webContents.getURL()) event.preventDefault();
  });

  if (WEB_URL) win.loadURL(WEB_URL);
  else win.loadFile(path.join(ROOT, "apps", "web", "dist", "index.html"));
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    const [win] = BrowserWindow.getAllWindows();
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });

  app.whenReady().then(async () => {
    try {
      createWindow(await startEngine());
    } catch (err) {
      quitting = true;
      stopEngine();
      dialog.showErrorBox("Quant Terminal could not start", err.message);
      app.quit();
    }
  });

  app.on("before-quit", () => {
    quitting = true;
    stopEngine();
  });
  app.on("window-all-closed", () => app.quit());
  process.on("exit", stopEngine);
}
