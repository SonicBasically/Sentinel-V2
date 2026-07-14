const { contextBridge } = require('electron');

// Expose a flag so Sentinel UI knows it's running inside Electron
contextBridge.exposeInMainWorld('sentinelEnv', {
  isElectron: true,
  platform: process.platform,
});
