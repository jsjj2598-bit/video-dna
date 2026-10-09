// Lightweight local project workspace. It keeps project context separate from
// analysis payloads so a user can return to the same work without a server DB.
const PROJECT_KEY = 'vdna_project_workspace';
const PROJECTS_KEY = 'vdna_projects_index';
const PROJECT_RESULTS_KEY = 'vdna_project_results';
let projectState = { id: '', name: '未命名项目', createdAt: Date.now(), updatedAt: Date.now(), assets: [] };

function newProjectId() { return 'project-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 7); }
function getProjectIndex() { try { const value = JSON.parse(localStorage.getItem(PROJECTS_KEY) || '[]'); return Array.isArray(value) ? value : []; } catch (_) { return []; } }
function updateProjectIndex() {
  const index = getProjectIndex().filter(p => p.id !== projectState.id);
  index.unshift({ id: projectState.id, name: projectState.name, createdAt: projectState.createdAt, updatedAt: projectState.updatedAt, assets: projectState.assets.slice(0, 100) });
  localStorage.setItem(PROJECTS_KEY, JSON.stringify(index.slice(0, 20)));
}

function loadProjectState() {
  try { projectState = Object.assign(projectState, JSON.parse(localStorage.getItem(PROJECT_KEY) || '{}')); } catch (_) {}
  if (!projectState.id) projectState.id = newProjectId();
  if (!projectState.updatedAt) projectState.updatedAt = projectState.createdAt || Date.now();
  if (!Array.isArray(projectState.assets)) projectState.assets = [];
  localStorage.setItem(PROJECT_KEY, JSON.stringify(projectState));
  updateProjectIndex();
  renderProjectState();
}

function saveProjectState() { projectState.updatedAt = Date.now(); localStorage.setItem(PROJECT_KEY, JSON.stringify(projectState)); updateProjectIndex(); renderProjectState(); }

function getProjectResults() {
  try { const value = JSON.parse(localStorage.getItem(PROJECT_RESULTS_KEY) || '{}'); return value && typeof value === 'object' ? value : {}; } catch (_) { return {}; }
}

function resultSnapshot(result) {
  if (!result || typeof result !== 'object') return null;
  return {
    _session_id: result._session_id || currentSessionId || '', _source_file: result._source_file || '',
    _frame_base: result._frame_base || '', _video_url: result._video_url || '',
    meta: result.meta || {}, audio: result.audio || {}, summary: result.summary || '',
    summary_method: result.summary_method || '', shots: Array.isArray(result.shots) ? result.shots : [],
    _cut_plan: result._cut_plan || null,
  };
}

function saveProjectResultSnapshot(result) {
  if (!projectState.id || !result || !currentSessionId) return;
  const all = getProjectResults();
  const snapshot = { savedAt: Date.now(), result: resultSnapshot(result) };
  all[projectState.id + ':' + currentSessionId] = snapshot;
  const keys = Object.keys(all).sort((a, b) => (all[b].savedAt || 0) - (all[a].savedAt || 0));
  const trimmed = {}; keys.slice(0, 12).forEach(k => { trimmed[k] = all[k]; });
  try {
    const encoded = JSON.stringify(trimmed);
    if (encoded.length <= 4 * 1024 * 1024) localStorage.setItem(PROJECT_RESULTS_KEY, encoded);
  } catch (_) { /* localStorage quota must not interrupt analysis */ }
  if (window.electronAPI?.saveProjectSnapshot) {
    window.electronAPI.saveProjectSnapshot(projectState.id, currentSessionId, snapshot)
      .catch(error => showErrorPanel('保存分析快照失败', '当前结果仍可使用，但请另存工程文件以保护修改。', error, '项目'));
  }
}

function loadProjectResultSnapshot(sessionId) {
  if (!projectState.id || !sessionId) return null;
  return getProjectResults()[projectState.id + ':' + sessionId]?.result || null;
}

async function loadProjectResultSnapshotAsync(sessionId) {
  const cached = loadProjectResultSnapshot(sessionId);
  if (cached || !window.electronAPI?.loadProjectSnapshot) return cached;
  const stored = await window.electronAPI.loadProjectSnapshot(projectState.id, sessionId);
  if (stored?.result) {
    const all = getProjectResults();
    all[projectState.id + ':' + sessionId] = stored;
    try { localStorage.setItem(PROJECT_RESULTS_KEY, JSON.stringify(all)); } catch (_) { /* disk copy remains authoritative */ }
    return stored.result;
  }
  return null;
}

function renderProjectState() {
  const name = projectState.name || '未命名项目';
  const count = projectState.assets.length;
  const analyzed = projectState.assets.filter(a => a.status === 'done').length;
  const label = count ? `${count} 个素材 · ${analyzed} 个已分析` : '还没有素材';
  const nameEl = document.getElementById('projectName');
  const metaEl = document.getElementById('projectMeta');
  const miniName = document.getElementById('projectMiniName');
  const miniMeta = document.getElementById('projectMiniMeta');
  if (nameEl) nameEl.textContent = name;
  if (metaEl) metaEl.textContent = label;
  if (miniName) miniName.textContent = name;
  if (miniMeta) miniMeta.textContent = label;
  const strip = document.getElementById('assetStrip');
  renderRecentProjects();
  if (!strip) return;
  strip.innerHTML = projectState.assets.length ? projectState.assets.map((asset, index) => `
    <button class="asset-chip ${asset.status === 'done' ? 'done' : ''} ${asset.name === (currentFile && currentFile.name) || asset.path === window.__currentAssetPath ? 'active' : ''}" onclick="selectProjectAsset(${index})" title="${esc(asset.name)}">
      <span class="asset-chip-icon">${asset.status === 'done' ? '✓' : '◌'}</span><span class="asset-chip-name">${esc(asset.name)}</span><span class="asset-chip-size">${asset.size}</span>
    </button>`).join('') : '<div class="asset-empty">项目素材会显示在这里。支持拖入多个视频，先选择一个开始分析。</div>';
}

function projectAddAsset(file) {
  if (!file || projectState.assets.some(a => a.name === file.name && a.sizeBytes === file.size)) return;
  projectState.assets.push({ name: file.name, sizeBytes: file.size, size: formatAssetSize(file.size), status: 'queued', addedAt: Date.now() });
  saveProjectState();
}

function projectAddAssetPath(filePath) {
  if (!filePath) return;
  const path = String(filePath);
  const name = path.split(/[\\/]/).pop() || 'video';
  const existing = projectState.assets.find(a => a.path === path || (!a.path && a.name === name));
  if (existing) { existing.path = path; window.__currentAssetPath = path; saveProjectState(); return; }
  projectState.assets.push({ name, path, size: '桌面文件', status: 'queued', addedAt: Date.now() });
  window.__currentAssetPath = path;
  saveProjectState();
}

function formatAssetSize(bytes) { return bytes >= 1024 * 1024 * 1024 ? (bytes / 1024 / 1024 / 1024).toFixed(1) + ' GB' : (bytes / 1024 / 1024).toFixed(1) + ' MB'; }

function markCurrentAsset(status) {
  if (!currentFile && !window.__currentAssetPath) return;
  const asset = projectState.assets.find(a => (currentFile && a.name === currentFile.name && a.sizeBytes === currentFile.size) || (window.__currentAssetPath && a.path === window.__currentAssetPath));
  if (asset) { asset.status = status; asset.sessionId = currentSessionId || asset.sessionId; saveProjectState(); }
}

function selectProjectAsset(index) {
  const asset = projectState.assets[index];
  if (!asset) return;
  if (asset.path && window.electronAPI?.analyzePath) {
    window.__currentAssetPath = asset.path;
    analyzeDesktopPath(asset.path);
    return;
  }
  toast('已选择素材「' + asset.name + '」。请重新拖入或使用上传按钮加载原文件。', 'info', 4000);
  document.getElementById('fileInput')?.click();
}

function openProjectSettings() {
  const input = document.getElementById('projectNameInput');
  if (input) input.value = projectState.name || '';
  renderRecentProjects();
  openModal('modalProject');
}

function renderRecentProjects() {
  const list = document.getElementById('recentProjects');
  if (!list) return;
  const projects = getProjectIndex();
  list.innerHTML = projects.length ? projects.map(p => `
    <div class="recent-project ${p.id === projectState.id ? 'active' : ''}">
      <button class="recent-project-main" onclick="switchLocalProject('${esc(p.id)}')"><strong>${esc(p.name || '未命名项目')}</strong><small>${(p.assets || []).length} 个素材 · ${p.updatedAt ? new Date(p.updatedAt).toLocaleString('zh-CN') : '未保存'}</small></button>
      ${p.id !== projectState.id ? `<button class="recent-project-del" title="删除项目索引" onclick="deleteLocalProject('${esc(p.id)}')">×</button>` : ''}
    </div>`).join('') : '<div class="recent-project-empty">还没有其他本机项目</div>';
}

async function switchLocalProject(id) {
  const target = getProjectIndex().find(p => p.id === id);
  if (!target || target.id === projectState.id) return;
  projectState = Object.assign({ id: newProjectId(), name: '未命名项目', createdAt: Date.now(), updatedAt: Date.now(), assets: [] }, target);
  currentFile = null; currentResult = null; currentSessionId = null; window.__currentAssetPath = '';
  document.getElementById('resultArea').innerHTML = '';
  document.getElementById('analyzeBtn').disabled = true;
  saveProjectState(); closeModal('modalProject');
  toast('已切换到项目：' + projectState.name, 'success');
  const sessionId = projectState.assets.find(a => a.sessionId)?.sessionId;
  if (sessionId && typeof restoreProjectSession === 'function') await restoreProjectSession(sessionId);
}

function deleteLocalProject(id) {
  const target = getProjectIndex().find(p => p.id === id);
  if (!target || !confirm('删除本机项目索引「' + (target.name || '未命名项目') + '」？不会删除历史分析和原始视频。')) return;
  localStorage.setItem(PROJECTS_KEY, JSON.stringify(getProjectIndex().filter(p => p.id !== id)));
  renderRecentProjects();
  toast('项目索引已删除', 'info');
}

function renameProject() { openProjectSettings(); }

function saveProjectName() {
  const input = document.getElementById('projectNameInput');
  const value = (input?.value || '').trim();
  if (!value) { toast('项目名称不能为空', 'error'); return; }
  projectState.name = value;
  saveProjectState();
  closeModal('modalProject');
  toast('项目名称已保存', 'success');
}

async function exportProject() {
  if (!window.electronAPI?.saveProject) { toast('请使用桌面版保存 .vdna 工程文件', 'info'); return; }
  try {
    const project = JSON.parse(JSON.stringify(projectState));
    project.currentSessionId = currentSessionId || null;
    project.currentAssetPath = window.__currentAssetPath || '';
    project.resultSnapshots = {};
    const sessionIds = [...new Set([currentSessionId, ...project.assets.map(asset => asset.sessionId)].filter(Boolean))];
    for (const sessionId of sessionIds) {
      const snapshot = await loadProjectResultSnapshotAsync(sessionId);
      if (snapshot) project.resultSnapshots[sessionId] = { savedAt: Date.now(), result: snapshot };
    }
    const path = await window.electronAPI.saveProject(project);
    if (path) { closeModal('modalProject'); toast('工程已保存：' + path, 'success', 5000); }
  } catch (error) { showErrorPanel('保存工程失败', '当前项目仍保留在本机，可以修复后重试。', error, '项目文件'); }
}

async function importProject() {
  if (!window.electronAPI?.openProject) { toast('请使用桌面版打开 .vdna 工程文件', 'info'); return; }
  try {
    const imported = await window.electronAPI.openProject();
    if (!imported) return;
    if (!imported.name || !Array.isArray(imported.assets)) throw new Error('工程缺少项目名称或素材列表');
    projectState = { id: newProjectId(), name: String(imported.name).slice(0, 80), createdAt: imported.createdAt || Date.now(), updatedAt: Date.now(), assets: imported.assets.slice(0, 500) };
    window.__currentAssetPath = imported.currentAssetPath || '';
    if (imported.resultSnapshots && typeof imported.resultSnapshots === 'object') {
      for (const [sessionId, snapshot] of Object.entries(imported.resultSnapshots)) {
        if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(sessionId) || !snapshot?.result) continue;
        try {
          if (window.electronAPI?.saveProjectSnapshot) await window.electronAPI.saveProjectSnapshot(projectState.id, sessionId, snapshot);
          const all = getProjectResults();
          all[projectState.id + ':' + sessionId] = snapshot;
          try { localStorage.setItem(PROJECT_RESULTS_KEY, JSON.stringify(all)); } catch (_) { /* disk copy remains authoritative */ }
        } catch (error) {
          showErrorPanel('部分分析快照未能恢复', '项目素材已打开；请检查磁盘空间和权限。', error, '项目文件');
        }
      }
    }
    saveProjectState();
    closeModal('modalProject');
    toast('工程已打开：' + projectState.name, 'success');
    const sessionId = imported.currentSessionId || projectState.assets.find(a => a.sessionId)?.sessionId;
    if (sessionId) await restoreProjectSession(sessionId);
  } catch (error) { showErrorPanel('打开工程失败', '工程文件未被应用，当前项目保持不变。', error, '项目文件'); }
}

async function restoreProjectSession(sessionId) {
  try {
    const response = await fetch('/api/history/' + encodeURIComponent(sessionId));
    if (!response.ok) return;
    const data = await response.json();
    currentResult = data; currentSessionId = data._session_id || sessionId;
    const snapshot = await loadProjectResultSnapshotAsync(currentSessionId);
    if (snapshot) currentResult = Object.assign({}, data, snapshot, { _session_id: currentSessionId });
    renderResult(currentResult, null, { history: true });
    toast(snapshot ? '已恢复最近一次分析结果和人工修改' : '已恢复最近一次分析结果', 'success');
  } catch (_) { toast('工程已打开，但最近分析结果暂时无法恢复', 'info', 4500); }
}

function createProject() {
  try {
    if (projectState.assets.length && !window.confirm('新建项目会清空当前项目的本地素材列表，历史分析不会删除。继续吗？')) return;
    projectState = { id: newProjectId(), name: '未命名项目', createdAt: Date.now(), updatedAt: Date.now(), assets: [] };
    currentFile = null; currentResult = null; currentSessionId = null; window.__currentAssetPath = '';
    const result = document.getElementById('resultArea');
    const analyze = document.getElementById('analyzeBtn');
    if (result) result.innerHTML = '';
    if (analyze) analyze.disabled = true;
    saveProjectState();
    toast('已创建新项目', 'success');
  } catch (error) {
    if (typeof showErrorPanel === 'function') showErrorPanel('新建项目失败', '当前项目没有被删除，请重试。', error, '项目');
    else toast('新建项目失败：' + error.message, 'error');
  }
}
window.createProject = createProject;
window.newProject = createProject;

function editShot(index) {
  const shot = window.__lastShots?.[index];
  if (!shot) return;
  document.getElementById('shotEditIndex').value = index;
  document.getElementById('shotEditStart').value = Number(shot.start || 0).toFixed(3);
  document.getElementById('shotEditEnd').value = Number(shot.end || 0).toFixed(3);
  document.getElementById('shotEditTransition').value = shot.transition || 'cut';
  document.getElementById('shotEditNote').value = shot.review_note || '';
  openModal('modalShot');
}

function saveEditingShot() {
  const index = Number(document.getElementById('shotEditIndex').value);
  const shot = window.__lastShots?.[index];
  if (!shot) return;
  const start = Number(document.getElementById('shotEditStart').value);
  const end = Number(document.getElementById('shotEditEnd').value);
  const duration = currentResult?.meta?.duration || Number.MAX_SAFE_INTEGER;
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start || end > duration) { toast('时间范围无效，请检查起止时间', 'error'); return; }
  shot.start = start; shot.end = end; shot.duration = end - start;
  shot.transition = document.getElementById('shotEditTransition').value;
  shot.review_note = document.getElementById('shotEditNote').value.trim();
  shot.reviewed = true;
  closeModal('modalShot');
  renderResult(currentResult, currentFile);
  saveProjectResultSnapshot(currentResult);
  toast('镜头已修改并标记为人工复核', 'success');
}

function removeEditingShot() {
  const index = Number(document.getElementById('shotEditIndex').value);
  if (!window.__lastShots?.[index] || !confirm('删除这个镜头？导出时也会移除它。')) return;
  window.__lastShots.splice(index, 1);
  if (currentResult) { currentResult.shots = window.__lastShots; currentResult.meta.total_shots = window.__lastShots.length; }
  closeModal('modalShot');
  renderResult(currentResult, currentFile);
  saveProjectResultSnapshot(currentResult);
  toast('镜头已删除', 'success');
}

document.addEventListener('DOMContentLoaded', () => {
  loadProjectState();
  const drop = document.getElementById('dropZone');
  if (drop) {
    ['dragenter', 'dragover'].forEach(type => drop.addEventListener(type, event => { event.preventDefault(); drop.classList.add('drag'); }));
    ['dragleave', 'drop'].forEach(type => drop.addEventListener(type, event => { event.preventDefault(); drop.classList.remove('drag'); }));
    drop.addEventListener('drop', event => { if (typeof enqueueFiles === 'function') enqueueFiles(event.dataTransfer?.files); else { const file = event.dataTransfer?.files?.[0]; if (file) setFile(file); } });
  }
});
