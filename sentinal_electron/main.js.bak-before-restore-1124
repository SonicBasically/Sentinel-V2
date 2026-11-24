const { app, BrowserWindow, Tray, Menu, nativeImage, shell, ipcMain } = require('electron');

// Required for speech synthesis and media in Electron
app.commandLine.appendSwitch('enable-speech-dispatcher');
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

const HOME = process.env.HOME || '/home/thomasgomez';
const PROJECT_DIR = path.join(HOME, 'Desktop/OG_Drive/GitHub/Sentinel-V2');
const VENV_PYTHON = path.join(PROJECT_DIR, '.venv/bin/python');
const SERVER_PY = path.join(PROJECT_DIR, 'server.py');
const OLLAMA_BIN = '/snap/ollama/current/bin/ollama';

let mainWindow = null;
let tray = null;
let backendProc = null;
let ollamaProc = null;

// ── START UI SERVER ──
function startUIServer() {
  const { spawn, execFileSync } = require('child_process');
  let tailscaleIP = '';
  try {
    tailscaleIP = execFileSync('tailscale', ['ip', '-4'], { encoding: 'utf8', timeout: 3000 }).trim().split(/\s+/)[0];
    if (!/^100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.\d{1,3}\.\d{1,3}$/.test(tailscaleIP)) tailscaleIP = '';
  } catch (err) {
    console.warn('[Network] Tailscale IPv4 unavailable; UI will listen on localhost only.');
  }
  for (const address of ['127.0.0.1', ...(tailscaleIP ? [tailscaleIP] : [])]) {
    const uiProc = spawn('python3', ['-m', 'http.server', '8766', '--bind', address], {
      cwd: PROJECT_DIR,
      detached: false,
    });
    uiProc.stderr.on('data', d => console.error('[ui]', d.toString().trim()));
    console.log('UI server listening on ' + address + ':8766');
  }
}

// ── START BACKEND (only if not already running) ──
function startBackend() {
  const http = require('http');
  http.get('http://localhost:8765/', res => {
    console.log('Backend already running, skipping start.');
  }).on('error', () => {
    console.log('Starting backend...');
    backendProc = spawn(VENV_PYTHON, [SERVER_PY], {
      cwd: PROJECT_DIR,
      env: { ...process.env },
      detached: false,
    });
    backendProc.stdout.on('data', d => console.log('[backend]', d.toString().trim()));
    backendProc.stderr.on('data', d => console.error('[backend]', d.toString().trim()));
    backendProc.on('exit', code => { console.log('Backend exited:', code); backendProc = null; });
  }).end();
}

// ── START OLLAMA (only if not already running) ──
function startOllama() {
  if (ollamaProc) return;
  const http = require('http');
  http.get('http://localhost:11434/api/tags', res => {
    console.log('Ollama already running, skipping start.');
  }).on('error', () => {
    console.log('Starting Ollama...');
    ollamaProc = spawn(OLLAMA_BIN, ['serve'], {
      env: { ...process.env, OLLAMA_ORIGINS: '*', OLLAMA_HOST: '0.0.0.0' },
      detached: false,
    });
    ollamaProc.stdout.on('data', d => console.log('[ollama]', d.toString().trim()));
    ollamaProc.stderr.on('data', d => console.error('[ollama]', d.toString().trim()));
    ollamaProc.on('exit', code => { console.log('Ollama exited:', code); ollamaProc = null; });
  }).end();
}

// ── KILL EXISTING PROCESSES ──
function killExisting(cb) {
  // launch.sh already kills processes, so just wait briefly
  setTimeout(cb, 500);
}

// ── PICK MONITOR ──
// SENTINEL_MONITOR: right (default) | left | primary | 1,2,3... (left to right)
function pickDisplay() {
  const { screen } = require('electron');
  const want = (process.env.SENTINEL_MONITOR || 'right').toLowerCase();
  if (want === 'primary') return screen.getPrimaryDisplay();
  const byX = [...screen.getAllDisplays()].sort((a, b) => a.bounds.x - b.bounds.x);
  if (want === 'left') return byX[0];
  if (/^\d+$/.test(want) && byX[Number(want) - 1]) return byX[Number(want) - 1];
  return byX[byX.length - 1];
}

// ── CREATE WINDOW ──
const ICON_PATH = path.join(__dirname, 'icon.png');

function createWindow() {
  // Grant mic and media permissions automatically
  const { session } = require('electron');
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    const allowed = ['media', 'microphone', 'audioCapture', 'notifications', 'speech-recognition'];
    callback(allowed.includes(permission));
  });
  const target = pickDisplay();
  mainWindow = new BrowserWindow({
    x: target.bounds.x,
    y: target.bounds.y,
    width: target.bounds.width,
    height: target.bounds.height,
    minWidth: 900,
    minHeight: 600,
    title: 'Sentinel V2',
    icon: ICON_PATH,
    backgroundColor: '#080808',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      permissions: ['media'],
    },
    show: false,
    autoHideMenuBar: true,
  });

  // Wait for backend then load via http server (avoids file:// fetch restrictions)
  let attempts = 0;
  function tryLoad() {
    attempts++;
    const http = require('http');
    const req = http.get('http://localhost:8765/', res => {
      // Backend ready — load via http server
      mainWindow.loadURL('http://localhost:8766/sentinel_v2.html');
    });
    req.on('error', () => {
      if (attempts < 20) setTimeout(tryLoad, 1000);
      else mainWindow.loadURL('http://localhost:8766/sentinel_v2.html');
    });
    req.end();
  }
  setTimeout(tryLoad, 2000);

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    if (!process.env.SENTINEL_WINDOWED) mainWindow.setFullScreen(true);
    if (!process.env.SENTINEL_QUIET) mainWindow.webContents.openDevTools({ mode: 'detach' });
  });

  // F11 toggles fullscreen
  mainWindow.webContents.on('before-input-event', (e, input) => {
    if (input.type === 'keyDown' && input.key === 'F11') {
      mainWindow.setFullScreen(!mainWindow.isFullScreen());
      e.preventDefault();
    }
  });

  mainWindow.on('close', e => {
    e.preventDefault();
    mainWindow.hide();
  });

  mainWindow.on('closed', () => { mainWindow = null; });
}

// ── TRAY ──
function createTray() {
  const icon = nativeImage.createFromPath(ICON_PATH).resize({ width: 22, height: 22 });
  tray = new Tray(icon);

  const menu = Menu.buildFromTemplate([
    { label: 'Sentinel V2', enabled: false },
    { type: 'separator' },
    { label: 'Show', click: () => { if(mainWindow) mainWindow.show(); } },
    { label: 'Hide', click: () => { if(mainWindow) mainWindow.hide(); } },
    { type: 'separator' },
    { label: 'Restart Backend', click: () => {
        if(backendProc) { backendProc.kill(); backendProc = null; }
        setTimeout(startBackend, 500);
    }},
    { label: 'Restart Ollama', click: () => {
        if(ollamaProc) { ollamaProc.kill(); ollamaProc = null; }
        setTimeout(startOllama, 500);
    }},
    { type: 'separator' },
    { label: 'Quit Sentinel', click: () => {
        if(backendProc) backendProc.kill();
        if(ollamaProc) ollamaProc.kill();
        mainWindow = null;
        app.exit(0);
    }},
  ]);

  tray.setToolTip('Sentinel V2');
  tray.setContextMenu(menu);
  tray.on('click', () => { if(mainWindow) mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show(); });
}

// ── APP LIFECYCLE ──
app.whenReady().then(() => {
  app.setName('Sentinel V2');
  // Set app icon for Linux taskbar
  try { app.setIcon(nativeImage.createFromPath(ICON_PATH)); } catch(e) {}
  killExisting(() => {
    startBackend();
    startOllama();
    startUIServer();
    createWindow();
    createTray();
  });
});

app.on('window-all-closed', e => e.preventDefault()); // Keep running in tray

app.on('before-quit', () => {
  if(backendProc) backendProc.kill();
  if(ollamaProc) ollamaProc.kill();
});

app.on('activate', () => { if(mainWindow) mainWindow.show(); });
