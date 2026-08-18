"use strict";

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  platform: process.platform,

  openFile: () => ipcRenderer.invoke('dialog:openFile'),

  saveFile: (defaultName) => ipcRenderer.invoke('dialog:saveFile', defaultName),

  onExport: (callback) => {
    const handler = (_event, fmt) => callback(fmt);
    ipcRenderer.on('export', handler);
    return () => ipcRenderer.removeListener('export', handler);
  },

  onFileOpened: (callback) => {
    const handler = (_event, filePath) => callback(filePath);
    ipcRenderer.on('file-opened', handler);
    return () => ipcRenderer.removeListener('file-opened', handler);
  },
});