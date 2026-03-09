const { contextBridge, ipcRenderer } = require('electron');

const acquittifyApi = {
  getVaultRoot: () => ipcRenderer.invoke('vault:get-root'),
  getBuildInfo: () => ipcRenderer.invoke('app:get-build-info'),
  pickVaultRoot: () => ipcRenderer.invoke('vault:pick-root'),
  listVault: (relPath = '') => ipcRenderer.invoke('vault:list', relPath),
  readVaultFile: (relPath) => ipcRenderer.invoke('vault:read', relPath),
  getVaultFileUrl: (relPath) => ipcRenderer.invoke('vault:file-url', relPath),
  writeVaultFile: (path, content) => ipcRenderer.invoke('vault:write', { path, content }),
  createVaultNote: (payload = {}) => ipcRenderer.invoke('vault:create-note', payload),
  createVaultFolder: (payload = {}) => ipcRenderer.invoke('vault:create-folder', payload),
  renameVaultPath: (payload = {}) => ipcRenderer.invoke('vault:rename-path', payload),
  deleteVaultPath: (payload = {}) => ipcRenderer.invoke('vault:delete-path', payload),
  ensureExtractedNote: (path, force = false) => ipcRenderer.invoke('vault:ensure-extracted-note', { path, force }),
  importVaultFiles: (payload = {}) => ipcRenderer.invoke('vault:import-files', payload),
  searchVault: (query) => ipcRenderer.invoke('vault:search', query),
  getGraph: () => ipcRenderer.invoke('vault:graph'),
  getOntologyGraph: () => ipcRenderer.invoke('vault:ontology-graph'),
  getOntologyGraphMulti: (payload = {}) => ipcRenderer.invoke('vault:ontology-graph-multi', payload),
  getCaselawJurisdictions: () => ipcRenderer.invoke('vault:caselaw-jurisdictions'),
  bootstrapCasefile: (payload = {}) => ipcRenderer.invoke('casefile:bootstrap', payload),
  runAgent: (payload) => ipcRenderer.invoke('agent:run', payload),
  runAgentStream: (payload) => ipcRenderer.invoke('agent:run-stream', payload),
  onAgentStream: (handler) => {
    const wrapped = (_event, payload) => {
      try {
        handler(payload);
      } catch {
        // swallow renderer listener errors
      }
    };
    ipcRenderer.on('agent:stream', wrapped);
    return () => ipcRenderer.removeListener('agent:stream', wrapped);
  },
  reloadAppWithCode: () => ipcRenderer.invoke('app:reload-with-code'),
  onWindowGeometryChanged: (handler) => {
    const wrapped = (_event, payload) => {
      try {
        handler(payload);
      } catch {
        // swallow renderer listener errors
      }
    };
    ipcRenderer.on('window:geometry-changed', wrapped);
    return () => ipcRenderer.removeListener('window:geometry-changed', wrapped);
  }
};

if (process.contextIsolated) {
  contextBridge.exposeInMainWorld('acquittifyApi', acquittifyApi);
} else {
  window.acquittifyApi = acquittifyApi;
}
