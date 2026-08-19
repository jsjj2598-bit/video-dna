/**
 * Video DNA Analyzer — Electron Desktop Main Process
 * 
 * Spawns the Python FastAPI backend as a child process,
 * opens a native window, and cleans up on exit.
 */
const { app, BrowserWindow, Menu, dialog, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

const PORT = 8000;
const BACKEND_URL = `http://127.0.0.1:${PORT}`;

let pythonProcess = null;
let mainWindow = null;

// ── Detect Python executable ──
function findPython() {
  const candidates = [];
  const root = path.resolve(__dirname, '..');
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

function startBackend() {
  const cwd = path.resolve(__dirname, '..');
  
  // Ensure uploads dir exists
  const fs = require('fs');
  const uploadsDir = path.join(cwd, 'uploads');
  if (!fs.existsSync(uploadsDir)) fs.mkdirSync(uploadsDir, { recursive: true });

  // 打包后，backend.exe 在 resources 目录；开发模式在 dist 目录
  const backendExe = app.isPackaged
    ? path.join(process.resourcesPath, 'backend.exe')
    : path.join(cwd, 'dist', 'backend.exe');

  if (!fs.existsSync(backendExe)) {
    console.error('Backend executable not found:', backendExe);
    return;
  }

  console.log(`[electron] Starting backend: ${backendExe}`);

  pythonProcess = spawn(backendExe, [], {
    cwd: path.dirname(backendExe),
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env },
  });

  pythonProcess.stdout.on('data', (data) => {
    console.log(`[backend] ${data.toString().trim()}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`[backend:err] ${data.toString().trim()}`);
  });

  pythonProcess.on('exit', (code) => {
    console.log(`[electron] Backend exited with code ${code}`);
    pythonProcess = null;
  });

  return pythonProcess;
}

function waitForBackend(retries = 30, interval = 500) {
  return new Promise((resolve, reject) => {
    const http = require('http');
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
  const fs = require('fs');
  const pr = path.resolve(__dirname, '..');
  const backendExe = app.isPackaged
    ? path.join(process.resourcesPath, 'backend.exe')
    : path.join(pr, 'dist', 'backend.exe');
  const ok = fs.existsSync(backendExe) ||
             fs.existsSync(path.join(pr, '.venv')) ||
             fs.existsSync(path.join(pr, 'app', 'main.py'));
  if (!ok) {
    const html = `<!DOCTYPE html><html><body style="background:#1a1d23;color:#e0e2e8;font-family:system-ui;padding:40px">
<h2 style="color:#5b8cff">Video DNA Analyzer</h2>
<p style="color:#8a90a0">Portable mode needs Python backend running.</p>
<hr style="border-color:#2a2f3a">
<h3>1. Install</h3>
<pre style="background:#22252e;padding:12px;border-radius:8px">python -m venv .venv
.venv\Scripts\pip install -r requirements.txt</pre>
<h3>2. Start backend</h3>
<pre style="background:#22252e;padding:12px;border-radius:8px">.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000</pre>
<h3>3. Refresh</h3>
<button onclick="location.reload()" style="background:#5b8cff;border:none;color:#fff;padding:8px 20px;border-radius:6px;cursor:pointer">Refresh</button>
<p>Or use start_desktop.cmd for one-click launch.</p>
</body></html>`;
    mainWindow = new BrowserWindow({width:900,height:600,title:'Setup Required',
      webPreferences:{nodeIntegration:false,contextIsolation:true}});
    mainWindow.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html));
    return;
  }
  startBackend();
  try { await waitForBackend(); } catch (e) {}
  createWindow();
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
    // Force kill after 3 seconds
    setTimeout(() => {
      if (pythonProcess) pythonProcess.kill('SIGKILL');
    }, 3000).unref();
  }
});

app.on('activate', () => {
  if (mainWindow === null) createWindow();
});