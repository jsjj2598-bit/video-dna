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
  const projectRoot = __dirname;  // electron/
  // Windows: .venv\Scripts\python.exe
  if (process.platform === 'win32') {
    candidates.push(path.join(projectRoot, '..', '.venv', 'Scripts', 'python.exe'));
    candidates.push(path.join(projectRoot, '..', '.venv', 'Scripts', 'python3.exe'));
    candidates.push('python');         // system PATH fallback
    candidates.push('python3');
  } else {
    // macOS / Linux
    candidates.push(path.join(projectRoot, '..', '.venv', 'bin', 'python'));
    candidates.push(path.join(projectRoot, '..', '.venv', 'bin', 'python3'));
    candidates.push('python3');
    candidates.push('python');
  }
  return candidates;
}

function startBackend() {
  // Use cwd = project root (parent of electron/)
  const cwd = path.resolve(__dirname, '..');

  // Ensure uploads dir exists
  const fs = require('fs');
  const uploadsDir = path.join(cwd, 'uploads');
  if (!fs.existsSync(uploadsDir)) fs.mkdirSync(uploadsDir, { recursive: true });

  const pythonCandidates = findPython();
  let pythonExe = null;

  for (const candidate of pythonCandidates) {
    const fullPath = path.isAbsolute(candidate) ? candidate : candidate;
    try {
      if (fs.existsSync(candidate) || candidate === candidate.split(path.sep).pop()) {
        // For simple names like 'python', just use them directly
        pythonExe = candidate;
        break;
      }
    } catch { continue; }
  }

  if (!pythonExe) {
    pythonExe = 'python'; // last resort
  }

  console.log(`[electron] Starting backend: ${pythonExe} -m uvicorn app.main:app`);
  
  pythonProcess = spawn(pythonExe, [
    '-m', 'uvicorn', 'app.main:app',
    '--host', '127.0.0.1',
    '--port', String(PORT),
    '--log-level', 'warning',
  ], {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: {
      ...process.env,
      PYTHONIOENCODING: 'utf-8',
      PYTHONUTF8: '1',
    },
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
  startBackend();

  try {
    await waitForBackend();
    console.log('[electron] Backend ready');
  } catch (err) {
    console.error('[electron] Backend startup failed:', err.message);
    // Still try to show the window — maybe it'll connect later
  }

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