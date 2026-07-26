import { contextBridge, ipcRenderer } from "electron";

/**
 * The renderer no longer opens its own WebSocket at all — that path never
 * worked reliably across real testing. Instead, this exposes a small
 * message-passing API backed by Electron's IPC, relaying to the ONE
 * gateway connection the main process owns (see electron/main.ts). IPC
 * between a preload/renderer and the main process doesn't touch browser
 * networking, proxy config, or file:// origin behavior at all — it's
 * Electron's own transport, unrelated to whatever was breaking before.
 */
contextBridge.exposeInMainWorld("cybertron", {
  gatewayPort: 8765,
  platform: process.platform,

  send: (json: string) => ipcRenderer.send("cybertron-send", json),

  onMessage: (callback: (data: string) => void) => {
    const listener = (_event: unknown, data: string) => callback(data);
    ipcRenderer.on("cybertron-message", listener);
    return () => ipcRenderer.removeListener("cybertron-message", listener);
  },

  onStatus: (callback: (status: string) => void) => {
    const listener = (_event: unknown, status: string) => callback(status);
    ipcRenderer.on("cybertron-ws-status", listener);
    return () => ipcRenderer.removeListener("cybertron-ws-status", listener);
  },

  getStatus: (): Promise<string> => ipcRenderer.invoke("cybertron-get-ws-status"),
  getToken: (): Promise<string | null> => ipcRenderer.invoke("cybertron-get-token"),
});
