"use strict";

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  platform: process.platform,

  openFile: () => ipcRenderer.invoke('dialog:openFile'),

  saveFile: (defaultName) => ipcRenderer.invoke('dialog:saveFile', defaultName),

  saveProject: (project) => ipcRenderer.invoke('project:save', project),
  openProject: () => ipcRenderer.invoke('project:open'),
  saveProjectSnapshot: (projectId, sessionId, snapshot) => ipcRenderer.invoke('project:snapshot:save', projectId, sessionId, snapshot),
  loadProjectSnapshot: (projectId, sessionId) => ipcRenderer.invoke('project:snapshot:load', projectId, sessionId),

  openDirectory: () => ipcRenderer.invoke('dialog:openDirectory'),

  showInFolder: (filePath) => ipcRenderer.invoke('shell:showInFolder', filePath),
  fileExists: (filePath) => ipcRenderer.invoke('fs:fileExists', filePath),

  analyzePath: (filePath, options) => ipcRenderer.invoke('analysis:uploadPath', filePath, options),
  getSecret: (key) => ipcRenderer.invoke('secret:get', key),
  setSecret: (key, value) => ipcRenderer.invoke('secret:set', key, value),
  deleteSecret: (key) => ipcRenderer.invoke('secret:delete', key),

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
