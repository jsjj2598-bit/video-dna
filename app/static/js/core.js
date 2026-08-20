// ── API bootstrap ──
const bootParams = new URLSearchParams(window.location.search);
const apiToken = bootParams.get('token') || sessionStorage.getItem('vdna_api_token') || '';
if (apiToken) {
  sessionStorage.setItem('vdna_api_token', apiToken);
  bootParams.delete('token');
  const cleanQuery = bootParams.toString();
  history.replaceState(null, '', window.location.pathname + (cleanQuery ? '?' + cleanQuery : '') + window.location.hash);
}
const nativeFetch = window.fetch.bind(window);
window.fetch = (resource, options = {}) => {
  const url = new URL(typeof resource === 'string' ? resource : resource.url, window.location.href);
  if (apiToken && url.origin === window.location.origin && url.pathname.startsWith('/api/')) {
    options = { ...options, headers: new Headers(options.headers || {}) };
    options.headers.set('X-VideoDNA-Token', apiToken);
  }
  return nativeFetch(resource, options);
};

// ── State ──
let currentResult = null;
let currentFile = null;
let currentCuts = null;       // 套用模板后的剪辑方案
let currentTemplateName = ''; // 模板来源（示例视频名）
let appliedVideoFile = null;  // 套用模板时上传的自己视频
let currentSessionId = null;  // 当前分析 session（历史/草稿/思考过程）
let compState = { components:[], models:[], plugins:[], skills:[] };

// ── Tab Switching ──
function switchTab(name, el) {
  document.querySelectorAll('.tab-panel').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  if (el) el.classList.add('active');
  const titles = {analyze:'视频分析',components:'AI 组件',history:'历史记录',studio:'AI 创作',settings:'设置',about:'关于'};
  const breads = {analyze:'上传视频并提取剪辑 DNA',components:'管理模型 / 插件 / 技能',history:'完整结果可回看',studio:'模板 / 分镜 / BGM 创作',settings:'配置引擎和行为',about:'版本和项目信息'};
  document.getElementById('pageTitle').textContent = titles[name] || 'Video DNA';
  document.getElementById('breadcrumb').textContent = breads[name] || '';
  if (name === 'components') loadComponents();
  if (name === 'history') renderHistory();
  if (name === 'studio') loadStudio();
}

// ── Upload ──
document.getElementById('dropZone').addEventListener('click', () => document.getElementById('fileInput').click());
['dragover','dragenter'].forEach(e => document.getElementById('dropZone').addEventListener(e, ev => { ev.preventDefault(); document.getElementById('dropZone').classList.add('drag'); }));
['dragleave','drop'].forEach(e => document.getElementById('dropZone').addEventListener(e, ev => { ev.preventDefault(); document.getElementById('dropZone').classList.remove('drag'); }));
document.getElementById('dropZone').addEventListener('drop', ev => { const f = ev.dataTransfer.files[0]; if (f) setFile(f); });
document.getElementById('fileInput').addEventListener('change', () => { if (document.getElementById('fileInput').files[0]) setFile(document.getElementById('fileInput').files[0]); });
document.getElementById('pluginInput').addEventListener('change', installPlugin);

function uploadVideo() { document.getElementById('fileInput').click(); }

function setFile(f) {
  if (!f) return;
  currentFile = f;
  document.querySelector('.drop-zone p').textContent = '✅ 已选择：' + f.name;
  document.querySelector('.drop-zone small').textContent = (f.size / 1024 / 1024).toFixed(1) + ' MB';
  document.getElementById('analyzeBtn').disabled = false;
  toast('📎 已选择 ' + f.name, 'info');
}

function startAnalysis() {
  if (!currentFile) { toast('❌ 请先选择视频', 'error'); return; }
  uploadFile(currentFile);
}

// ── Progress（右下角浮动面板，不阻塞页面操作） ──
function showP(status, sub) {
  hideMinBadge();
  document.getElementById('progressOverlay').classList.add('active');
  document.getElementById('pStatus').textContent = status || '正在分析...';
  document.getElementById('pSub').textContent = sub || '';
  document.getElementById('pFill').style.width = '0%';
}
function updateP(pct, status, sub) {
  document.getElementById('pFill').style.width = Math.min(pct,100) + '%';
  if (status) document.getElementById('pStatus').textContent = status;
  if (sub) document.getElementById('pSub').textContent = sub;
  // 最小化时同步徽章进度
  const badge = document.getElementById('progressMinBadge');
  const pmPct = document.getElementById('pmPct');
  if (badge && badge.style.display !== 'none' && pmPct) pmPct.textContent = Math.round(pct) + '%';
}
function hideP() {
  document.getElementById('progressOverlay').classList.remove('active');
  hideMinBadge();
}
function minimizeProgress() {
  document.getElementById('progressOverlay').classList.remove('active');
  const badge = document.getElementById('progressMinBadge');
  const pmPct = document.getElementById('pmPct');
  if (pmPct) pmPct.textContent = (document.getElementById('pFill').style.width || '0%');
  badge.style.display = 'flex';
  toast('⏳ 分析在后台进行中，可继续操作其他页面', 'info', 2500);
}
function restoreProgress() {
  hideMinBadge();
  document.getElementById('progressOverlay').classList.add('active');
}
function hideMinBadge() { const b = document.getElementById('progressMinBadge'); if (b) b.style.display = 'none'; }

// ── Toast ──
function toast(msg, type='info', dur=3500) {
  const c = document.getElementById('toastContainer');
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => { t.style.opacity='0'; t.style.transform='translateX(30px)'; t.style.transition='all .25s'; setTimeout(() => t.remove(), 250); }, dur);
}

// ── Settings ──
function getSettings() { try { return JSON.parse(localStorage.getItem('vdna_settings'))||{}; } catch { return {}; } }
function getSessionKeys() { try { return JSON.parse(sessionStorage.getItem('vdna_session_keys'))||{}; } catch { return {}; } }
function saveSettings() {
  const s = {
    detector: document.getElementById('setDetector').value,
    backend: document.getElementById('setBackend').value,
    export_fmt: document.getElementById('setExportFmt').value,
    download_dir: document.getElementById('setDownloadDir').value.trim(),
    theme: document.getElementById('setTheme').value,
    accent: getSettings().accent || '#6d5df6',
  };
  sessionStorage.setItem('vdna_session_keys', JSON.stringify({
    openai_key: document.getElementById('setOpenAIKey').value,
    qwen_key: document.getElementById('setQwenKey').value,
  }));
  localStorage.setItem('vdna_settings', JSON.stringify(s));
  applyTheme();
  toast('✅ 设置已保存', 'success');
}
function loadSettings() {
  const s = getSettings();
  let keys = getSessionKeys();
  if ((s.openai_key || s.qwen_key) && !keys.openai_key && !keys.qwen_key) {
    keys = { openai_key: s.openai_key || '', qwen_key: s.qwen_key || '' };
    sessionStorage.setItem('vdna_session_keys', JSON.stringify(keys));
    delete s.openai_key;
    delete s.qwen_key;
    localStorage.setItem('vdna_settings', JSON.stringify(s));
  }
  document.getElementById('setDetector').value = s.detector || 'content';
  document.getElementById('setBackend').value = s.backend || 'auto';
  document.getElementById('setOpenAIKey').value = keys.openai_key || '';
  document.getElementById('setQwenKey').value = keys.qwen_key || '';
  document.getElementById('setExportFmt').value = s.export_fmt || 'cutmark';
  document.getElementById('setDownloadDir').value = s.download_dir || '';
  document.getElementById('setTheme').value = s.theme || 'dark';
  applyTheme();
}
function applyTheme() {
  const s = getSettings();
  const theme = document.getElementById('setTheme') ? document.getElementById('setTheme').value : (s.theme || 'dark');
  const accent = s.accent || '#6d5df6';
  document.documentElement.setAttribute('data-theme', theme);
  document.documentElement.style.setProperty('--accent', accent);
  document.documentElement.style.setProperty('--accent-2', accent);
  // 主色变体（浅化用于渐变尾端）
  const lighten = (hex, f) => {
    if (typeof hex !== 'string' || !/^#[0-9a-fA-F]{6}$/.test(hex)) return '#6d5df6';
    const n = parseInt(hex.slice(1), 16);
    const r = Math.min(255, Math.round(((n >> 16) & 255) + (255 - ((n >> 16) & 255)) * f));
    const g = Math.min(255, Math.round(((n >> 8) & 255) + (255 - ((n >> 8) & 255)) * f));
    const b = Math.min(255, Math.round((n & 255) + (255 - (n & 255)) * f));
    return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0');
  };
  document.documentElement.style.setProperty('--accent-3', lighten(accent, 0.45));
  document.querySelectorAll('.theme-dot').forEach(d => d.classList.toggle('active', d.dataset.c === accent));
  const logo = document.querySelector('.sidebar-brand .logo');
  if (logo) logo.style.background = 'linear-gradient(135deg,' + accent + ',' + lighten(accent, 0.45) + ')';
  const navActive = document.querySelector('.nav-item.active .icon-tile');
  if (navActive) navActive.style.background = 'linear-gradient(135deg,' + accent + ',' + lighten(accent, 0.3) + ')';
}
function pickDownloadDir() {
  if (window.electronAPI && window.electronAPI.openDirectory) {
    window.electronAPI.openDirectory().then(dir => { if (dir) document.getElementById('setDownloadDir').value = dir; });
  } else {
    toast('⚠️ 请在桌面版中选择目录（浏览器模式请手动输入路径）', 'info');
  }
}
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.theme-dot').forEach(dot => {
    dot.addEventListener('click', () => {
      const s = getSettings();
      s.accent = dot.dataset.c;
      localStorage.setItem('vdna_settings', JSON.stringify(s));
      applyTheme();
    });
  });

  // 原生菜单「打开视频…」使用主进程流式上传，避免 Base64 内存复制。
  if (window.electronAPI && window.electronAPI.onFileOpened) {
    window.electronAPI.onFileOpened(async (filePath) => {
      try {
        if (!filePath) return;
        if (window.switchTab) switchTab('analyze', document.querySelector('.nav-item'));
        await analyzeDesktopPath(filePath);
      } catch (e) {
        toast('❌ 打开文件失败: ' + e.message, 'error');
      }
    });
  }

  // 原生菜单「导出 EDL/FCP7 XML/Cutmark」
  if (window.electronAPI && window.electronAPI.onExport) {
    window.electronAPI.onExport((fmt) => {
      if (!currentResult) { toast('⚠️ 请先分析视频再导出', 'info'); return; }
      if (typeof dlExp === 'function') dlExp(fmt);
    });
  }
});
