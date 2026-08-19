/**
 * Video DNA Analyzer — Electron Desktop Main Process
 * 
 * Spawns the Python FastAPI backend as a child process,
 * opens a native window, and cleans up on exit.
 */
const { app, BrowserWindow, Menu, dialog, ipcMain } = require('electron');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const http = require('http');

const PORT = 8000;
const BACKEND_URL = `http://127.0.0.1:${PORT}`;

const LOG_FILE = path.join(require('os').tmpdir(), 'videodna-electron.log');
function log(...args) {
  const line = `[${new Date().toISOString()}] ${args.join(' ')}`;
  console.log(line);
  try { fs.appendFileSync(LOG_FILE, line + '\n'); } catch (_) {}
}

let pythonProcess = null;
let mainWindow = null;

// ── Detect Python executable ──
function findPython() {
  const candidates = [];
  const root = app.isPackaged
    ? process.resourcesPath
    : path.resolve(__dirname, '..');
  if (process.platform === 'win32') {
    candidates.push(path.join(root, '.venv', 'Scripts', 'python.exe'));
    candidates.push(path.join(root, '.venv', 'Scripts', 'python3.exe'));
    candidates.push(path.join(root, 'venv', 'Scripts', 'python.exe'));
    candidates.push('python');
    candidates.push('python3');
  } else {
    candidates.push(path.join(root, '.venv', 'bin', 'python'));
    candidates.push(path.join(root, '.venv', 'bin', 'python3'));
    candidates.push(path.join(root, 'venv', 'bin', 'python'));
    candidates.push('python3');
    candidates.push('python');
  }
  return candidates;
}

function isBackendUp() {
  return new Promise((resolve) => {
    const req = http.get(`${BACKEND_URL}/health`, (res) => {
      res.resume();
      resolve(res.statusCode === 200);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(1500, () => { req.destroy(); resolve(false); });
  });
}

function findBackendExe() {
  // macOS 下 PyInstaller onefile 产物无 .exe 后缀
  const name = process.platform === 'win32' ? 'backend.exe' : 'backend';
  const exe = app.isPackaged
    ? path.join(process.resourcesPath, name)
    : path.join(path.resolve(__dirname, '..'), 'dist', name);
  log('findBackendExe ->', exe, 'exists=' + fs.existsSync(exe), 'isPackaged=' + app.isPackaged);
  return exe;
}

function startBackend() {
  const cwd = path.resolve(__dirname, '..');

  // 若后端已在运行（如 start_desktop.cmd 已启动 uvicorn），跳过启动避免端口冲突
  if (pythonProcess) return pythonProcess;

  const backendExe = findBackendExe();
  let spawnCommand = null;

  if (fs.existsSync(backendExe)) {
    spawnCommand = {
      cmd: backendExe,
      args: [],
      cwd: path.dirname(backendExe),
    };
  } else {
    // 未编译 backend.exe 时，回退到 .venv 的 Python 源码启动
    const pyCandidates = process.platform === 'win32'
      ? [path.join(cwd, '.venv', 'Scripts', 'python.exe'), 'python']
      : [path.join(cwd, '.venv', 'bin', 'python'), 'python3'];
    const py = pyCandidates.find((p) => p === 'python' || fs.existsSync(p));
    if (!py) {
      console.error('[electron] 未找到 Python 解释器（.venv 或系统 python）');
      return null;
    }
    spawnCommand = {
      cmd: py,
      args: ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', String(PORT), '--log-level', 'warning'],
      cwd,
    };
  }

  console.log(`[electron] Starting backend: ${spawnCommand.cmd} ${spawnCommand.args.join(' ')}`);
  log('spawning:', spawnCommand.cmd, spawnCommand.args.join(' '), 'cwd=' + spawnCommand.cwd);

  pythonProcess = spawn(spawnCommand.cmd, spawnCommand.args, {
    cwd: spawnCommand.cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env },
    windowsHide: true,
  });

  pythonProcess.on('error', (err) => {
    log('SPAWN_ERROR:', err.message);
    console.error('[electron] spawn error:', err.message);
    pythonProcess = null;
  });

  pythonProcess.stdout.on('data', (data) => {
    console.log(`[backend] ${data.toString().trim()}`);
    try { fs.appendFileSync(LOG_FILE, '[backend] ' + data.toString().trim() + '\n'); } catch (_) {}
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[backend:err] ${data.toString().trim()}`);
    try { fs.appendFileSync(LOG_FILE, '[backend:err] ' + data.toString().trim() + '\n'); } catch (_) {}
  });

  pythonProcess.on('exit', (code) => {
    console.log(`[electron] Backend exited with code ${code}`);
    pythonProcess = null;
  });

  return pythonProcess;
}

function waitForBackend(retries = 30, interval = 500) {
  return new Promise((resolve, reject) => {
    let attempts = 0;

    const check = () => {
      attempts++;
      const req = http.get(`${BACKEND_URL}/health`, (res) => {
        if (res.statusCode === 200) {
          resolve();
        } else if (attempts < retries) {
          setTimeout(check, interval);
        } else {
          reject(new Error(`Backend unhealthy after ${retries * interval}ms`));
        }
      });
      req.on('error', () => {
        if (attempts < retries) {
          setTimeout(check, interval);
        } else {
          reject(new Error(`Backend unreachable after ${retries * interval}ms`));
        }
      });
      req.end();
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
      webSecurity: false,   // 加载本地后端页面需要，仅限本机
    },
  });
  console.log('Loading backend URL directly...');
  mainWindow.show();
  mainWindow.loadURL(BACKEND_URL);

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
<button onclick="location.reload()" style="background:#4f7dff;border:none;color:#fff;padding:8px 24px;border-radius:6px;cursor:pointer;margin-top:12px">重试</button>
<script>
let tries = 0;
setInterval(() => {
  fetch('http://127.0.0.1:8000/health', { cache: 'no-store' })
    .then((r) => { if (r.ok) location.reload(); })
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
  if (pythonProcess) {
    console.log('[electron] Killing backend process');
    pythonProcess.kill('SIGTERM');
    setTimeout(() => {
      if (pythonProcess) pythonProcess.kill('SIGKILL');
    }, 3000).unref();
  }
});

app.on('activate', () => {
  if (mainWindow === null) createWindow();
});