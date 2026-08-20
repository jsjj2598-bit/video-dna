/**
 * Video DNA Analyzer — Electron Desktop Main Process
 * 
 * Spawns the standalone Go backend as a child process,
 * opens a native window, and cleans up on exit.
 */
const { app, BrowserWindow, Menu, dialog, ipcMain, shell } = require('electron');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

const PORT = Number(process.env.VIDEODNA_PORT || 8000);
const BACKEND_URL = `http://127.0.0.1:${PORT}`;
const API_TOKEN = process.env.VIDEODNA_API_TOKEN || '';

function frontendUrl() {
  return API_TOKEN ? `${BACKEND_URL}/?token=${encodeURIComponent(API_TOKEN)}` : BACKEND_URL;
}

function uploadVideoPath(filePath, options = {}) {
  return new Promise((resolve, reject) => {
    const absolutePath = path.resolve(String(filePath || ''));
    let stat;
    try {
      stat = fs.statSync(absolutePath);
      if (!stat.isFile()) throw new Error('所选路径不是文件');
    } catch (error) {
      reject(error);
      return;
    }
    const boundary = `----VideoDNA${Date.now().toString(16)}`;
    const fields = { session_id: options.session_id || '' };
    if (options.openai_key) fields.openai_key = options.openai_key;
    if (options.qwen_key) fields.qwen_key = options.qwen_key;
    const fieldParts = Object.entries(fields).map(([name, value]) =>
      `--${boundary}\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n${String(value)}\r\n`
    ).join('');
    const fileHeader = `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${path.basename(absolutePath).replaceAll('"', '')}"\r\nContent-Type: application/octet-stream\r\n\r\n`;
    const prefix = Buffer.from(fieldParts + fileHeader, 'utf8');
    const suffix = Buffer.from(`\r\n--${boundary}--\r\n`, 'utf8');
    const detector = encodeURIComponent(options.detector || 'content');
    const backend = encodeURIComponent(options.backend || 'auto');
    const request = http.request({
      hostname: '127.0.0.1',
      port: PORT,
      path: `/api/analyze?detector=${detector}&backend=${backend}`,
      method: 'POST',
      headers: {
        'Content-Type': `multipart/form-data; boundary=${boundary}`,
        'Content-Length': prefix.length + stat.size + suffix.length,
        ...(API_TOKEN ? { 'X-VideoDNA-Token': API_TOKEN } : {}),
      },
    }, (response) => {
      let body = '';
      response.setEncoding('utf8');
      response.on('data', (chunk) => { body += chunk; });
      response.on('end', () => {
        let payload;
        try { payload = JSON.parse(body); } catch (_) { payload = { detail: body || response.statusMessage }; }
        if ((response.statusCode || 500) >= 400) reject(new Error(payload.detail || `上传失败 (${response.statusCode})`));
        else resolve(payload);
      });
    });
    request.on('error', reject);
    request.write(prefix);
    const stream = fs.createReadStream(absolutePath);
    stream.on('error', (error) => request.destroy(error));
    stream.on('end', () => request.end(suffix));
    stream.pipe(request, { end: false });
  });
}

const LOG_FILE = path.join(require('os').tmpdir(), 'videodna-electron.log');
function log(...args) {
  const line = `[${new Date().toISOString()}] ${args.join(' ')}`;
  console.log(line);
  try { fs.appendFileSync(LOG_FILE, line + '\n'); } catch (_) {}
}

let backendProcess = null;
let mainWindow = null;

function isBackendUp() {
  return new Promise((resolve) => {
    const req = http.get(`${BACKEND_URL}/health`, (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => {
        try {
          const payload = JSON.parse(body);
          resolve(res.statusCode === 200 && payload.service === 'video-dna-analyzer');
        } catch (_) {
          resolve(false);
        }
      });
    });
    req.on('error', () => resolve(false));
    req.setTimeout(1500, () => { req.destroy(); resolve(false); });
  });
}

function findBackendExe() {
  const name = process.platform === 'win32' ? 'backend.exe' : 'backend';
  const exe = app.isPackaged
    ? path.join(process.resourcesPath, name)
    : path.join(path.resolve(__dirname, '..'), 'dist', name);
  log('findBackendExe ->', exe, 'exists=' + fs.existsSync(exe), 'isPackaged=' + app.isPackaged);
  return exe;
}

function startBackend() {
  if (backendProcess) return backendProcess;

  const backendExe = findBackendExe();
  if (!fs.existsSync(backendExe)) {
    log('Go backend executable missing:', backendExe);
    return null;
  }
  const spawnCommand = { cmd: backendExe, args: [], cwd: path.dirname(backendExe) };

  console.log(`[electron] Starting backend: ${spawnCommand.cmd} ${spawnCommand.args.join(' ')}`);
  log('spawning:', spawnCommand.cmd, spawnCommand.args.join(' '), 'cwd=' + spawnCommand.cwd);

  backendProcess = spawn(spawnCommand.cmd, spawnCommand.args, {
    cwd: spawnCommand.cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: {
      ...process.env,
      VIDEODNA_DATA_DIR: app.getPath('userData'),
      VIDEODNA_API_TOKEN: API_TOKEN,
      VIDEODNA_PORT: String(PORT),
    },
    windowsHide: true,
  });

  backendProcess.on('error', (err) => {
    log('SPAWN_ERROR:', err.message);
    console.error('[electron] spawn error:', err.message);
    backendProcess = null;
  });

  backendProcess.stdout.on('data', (data) => {
    console.log(`[backend] ${data.toString().trim()}`);
    try { fs.appendFileSync(LOG_FILE, '[backend] ' + data.toString().trim() + '\n'); } catch (_) {}
  });

  backendProcess.stderr.on('data', (data) => {
    console.error(`[backend:err] ${data.toString().trim()}`);
    try { fs.appendFileSync(LOG_FILE, '[backend:err] ' + data.toString().trim() + '\n'); } catch (_) {}
  });

  backendProcess.on('exit', (code) => {
    console.log(`[electron] Backend exited with code ${code}`);
    backendProcess = null;
  });

  return backendProcess;
}

function waitForBackend(retries = 30, interval = 500) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = async () => {
      attempts++;
      if (await isBackendUp()) return resolve();
      if (attempts < retries) return setTimeout(check, interval);
      reject(new Error(`Backend unavailable after ${retries * interval}ms`));
    };
    check();
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    title: 'Video DNA Analyzer',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      // 应用仅加载同源 http://127.0.0.1:8000，无需关闭 webSecurity
    },
  });
  console.log('Loading backend URL directly...');
  mainWindow.show();
  mainWindow.loadURL(frontendUrl());

  // Build native app menu
  const menu = Menu.buildFromTemplate([
    {
      label: '文件',
      submenu: [
        {
          label: '打开视频…',
          accelerator: 'CmdOrCtrl+O',
          click: async () => {
            const result = await dialog.showOpenDialog(mainWindow, {
              properties: ['openFile'],
              filters: [
                { name: '视频文件', extensions: ['mp4', 'mov', 'mkv', 'webm', 'avi'] },
                { name: '所有文件', extensions: ['*'] },
              ],
            });
            if (!result.canceled && result.filePaths[0]) {
              mainWindow.webContents.send('file-opened', result.filePaths[0]);
            }
          },
        },
        { type: 'separator' },
        {
          label: '退出',
          accelerator: 'CmdOrCtrl+Q',
          click: () => app.quit(),
        },
      ],
    },
    {
      label: '导出',
      submenu: [
        { label: 'EDL (CMX3600)', click: () => mainWindow.webContents.send('export', 'edl') },
        { label: 'FCP7 XML', click: () => mainWindow.webContents.send('export', 'fcp7xml') },
        { label: 'Cutmark JSON', click: () => mainWindow.webContents.send('export', 'cutmark') },
      ],
    },
    {
      label: '开发者',
      submenu: [
        { role: 'reload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
  ]);

  Menu.setApplicationMenu(menu);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(async () => {
  const uploadsDir = path.join(app.getPath('userData'), 'uploads');
  if (!fs.existsSync(uploadsDir)) fs.mkdirSync(uploadsDir, { recursive: true });

  // preload.js 暴露的 openFile / saveFile IPC 通道
  ipcMain.handle('dialog:openFile', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openFile'],
      filters: [
        { name: '视频文件', extensions: ['mp4', 'mov', 'mkv', 'webm', 'avi'] },
        { name: '所有文件', extensions: ['*'] },
      ],
    });
    if (!result.canceled && result.filePaths[0]) {
      mainWindow.webContents.send('file-opened', result.filePaths[0]);
      return result.filePaths[0];
    }
    return null;
  });

  ipcMain.handle('dialog:saveFile', async (_event, defaultName) => {
    const result = await dialog.showSaveDialog(mainWindow, {
      defaultPath: defaultName || 'videodna_export',
    });
    return result.canceled ? null : result.filePath;
  });

  ipcMain.handle('dialog:openDirectory', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openDirectory', 'createDirectory'],
    });
    return result.canceled ? null : result.filePaths[0];
  });

  ipcMain.handle('shell:showInFolder', async (_event, filePath) => {
    if (!filePath) return false;
    try {
      if (require('fs').existsSync(filePath)) {
        shell.showItemInFolder(filePath);
      } else {
        shell.openPath(require('path').dirname(filePath));
      }
      return true;
    } catch (_) { return false; }
  });

  // 原生菜单使用流式 multipart 上传，不把大视频复制为 Base64 经过 IPC。
  ipcMain.handle('analysis:uploadPath', (_event, filePath, options) => uploadVideoPath(filePath, options));

  const alreadyUp = await isBackendUp();
  log('isBackendUp ->', alreadyUp);
  if (!alreadyUp) {
    startBackend();
    try {
      console.log('[electron] Waiting for backend...');
      await waitForBackend(180, 500);
      console.log('[electron] Backend ready!');
      log('Backend ready!');
    } catch (e) {
      console.error('[electron] Backend not ready:', e.message);
      log('Backend NOT ready:', e.message);
    }
  } else {
    console.log('[electron] Backend already running, skip spawn.');
  }

  createWindow();

  // 后端无法启动时显示可读错误页，而不是白屏；并每 5 秒自检，
  // 后端一旦就绪立即自动刷新加载主页面
  if (!(await isBackendUp())) {
    log('Backend down at window open, showing recovery page');
    const errHtml = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Video DNA Analyzer</title></head>
<body style="background:#0e1017;color:#e2e4ee;font-family:system-ui,'Microsoft YaHei';display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
<div style="max-width:520px;text-align:center">
<h2 style="color:#4f7dff">🧬 Video DNA Analyzer</h2>
<p style="color:#ffd166;font-size:15px">正在启动分析引擎…</p>
<p id="msg" style="color:#8a90a0;font-size:13px;line-height:1.8">首次启动需要解压并加载后端组件，大约需要 30~60 秒，请稍候。</p>
<button onclick="location.href='${frontendUrl()}'" style="background:#4f7dff;border:none;color:#fff;padding:8px 24px;border-radius:6px;cursor:pointer;margin-top:12px">重试</button>
<script>
let tries = 0;
setInterval(() => {
  fetch('${BACKEND_URL}/health', { cache: 'no-store' })
    .then((r) => { if (r.ok) location.href='${frontendUrl()}'; })
    .catch(() => {});
}, 5000);
</script>
</div></body></html>`;
    mainWindow.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(errHtml));
  } else {
    log('Backend up at window open');
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('will-quit', () => {
  if (backendProcess) {
    console.log('[electron] Killing backend process');
    backendProcess.kill('SIGTERM');
    setTimeout(() => {
      if (backendProcess) backendProcess.kill('SIGKILL');
    }, 3000).unref();
  }
});

app.on('activate', () => {
  if (mainWindow === null) createWindow();
});
