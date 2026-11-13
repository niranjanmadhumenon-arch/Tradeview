// The only bridge between the UI and the desktop: where the engine is and the
// token to talk to it. No file system, no Node, no IPC.
const { contextBridge } = require("electron");

function arg(name) {
  const prefix = `--${name}=`;
  const found = process.argv.find((a) => a.startsWith(prefix));
  return found ? found.slice(prefix.length) : "";
}

contextBridge.exposeInMainWorld("qt", {
  engineUrl: arg("qt-engine"),
  token: arg("qt-token"),
  platform: process.platform,
});
