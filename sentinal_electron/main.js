const { app, BrowserWindow, Tray, Menu, nativeImage, session, screen, ipcMain, Notification } = require('electron');

// Required for speech synthesis and media in Electron
app.commandLine.appendSwitch('enable-speech-dispatcher');
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
const path = require('path');
const http = require('http');
const { execFile, execFileSync } = require('child_process');
const fs = require('fs');

const HOME = process.env.HOME || '/home/thomasgomez';
const UI_URL = 'http://localhost:8766/sentinel_v2.html';
const BACKEND_URL = 'http://localhost:8765/';
const OLLAMA_URL = 'http://localhost:11434/api/tags';
// The backend and UI file server are systemd USER services (systemd/*.service).
// This app connects to them; it never starts its own copies.
const SERVICES = ['sentinel-backend.service', 'sentinel-ui.service'];
const ICON_PATH = path.join(__dirname, 'icon.png');

let mainWindow = null;
let tray = null;

// ── SYSTEMD USER SERVICES ──
function userctl(args) {
  const uid = process.getuid ? process.getuid() : 1000;
  const env = {
    ...process.env,
    XDG_RUNTIME_DIR: process.env.XDG_RUNTIME_DIR || `/run/user/${uid}`,
    DBUS_SESSION_BUS_ADDRESS: process.env.DBUS_SESSION_BUS_ADDRESS || `unix:path=/run/user/${uid}/bus`,
  };
  execFile('systemctl', ['--user', ...args], { env, timeout: 30000 }, (err, stdout, stderr) => {
    if (err) console.error('[services] systemctl --user', args.join(' '), 'failed:', (stderr || err.message).toString().trim());
    else console.log('[services] systemctl --user', args.join(' '), 'ok');
  });
}
function startServices() { userctl(['start', ...SERVICES]); }
function restartServices() { userctl(['restart', ...SERVICES]); }
function stopServices() { userctl(['stop', ...SERVICES]); }

// Synchronous variant for quit: the app must not exit before the services have stopped.
function userctlSync(args) {
  const uid = process.getuid ? process.getuid() : 1000;
  const env = {
    ...process.env,
    XDG_RUNTIME_DIR: process.env.XDG_RUNTIME_DIR || `/run/user/${uid}`,
    DBUS_SESSION_BUS_ADDRESS: process.env.DBUS_SESSION_BUS_ADDRESS || `unix:path=/run/user/${uid}/bus`,
  };
  try {
    execFileSync('systemctl', ['--user', ...args], { env, timeout: 20000, stdio: 'ignore' });
  } catch (err) {
    console.error('[services] systemctl --user', args.join(' '), 'failed');
  }
}

// ── API KEY ──
// The key lives in ~/.config/sentinel/.env (the backend reads it there too). The preload
// hands it to the page so the key popup is not needed on the desktop. Never logged.
function readApiKey() {
  try {
    const text = fs.readFileSync(path.join(HOME, '.config/sentinel/.env'), 'utf8');
    const m = text.match(/^SENTINEL_API_KEY=(.*)$/m);
    return m ? m[1].trim().replace(/^["']|["']$/g, '') : '';
  } catch (err) {
    return '';
  }
}
ipcMain.on('sentinel-get-key', e => { e.returnValue = readApiKey(); });
ipcMain.on('sentinel-has-key', e => { e.returnValue = !!readApiKey(); });

// First run: save a key typed in the setup page to ~/.config/sentinel/.env (mode 600),
// then restart the backend so it reads the new key.
function saveApiKey(key) {
  const file = path.join(HOME, '.config/sentinel/.env');
  fs.mkdirSync(path.dirname(file), { recursive: true });
  let lines = [];
  try { lines = fs.readFileSync(file, 'utf8').split('\n'); } catch (err) { /* new file */ }
  const kept = lines.filter(l => l.trim() !== '' && !/^SENTINEL_API_KEY=/.test(l));
  kept.push(`SENTINEL_API_KEY=${key}`);
  fs.writeFileSync(file, kept.join('\n') + '\n', { mode: 0o600 });
  fs.chmodSync(file, 0o600);
}
ipcMain.handle('sentinel-save-key', (e, key) => {
  const clean = String(key || '').trim();
  if (clean.length < 16 || /\s/.test(clean)) {
    return { ok: false, error: 'That does not look like a valid key.' };
  }
  saveApiKey(clean);
  userctl(['restart', 'sentinel-backend.service']);
  return { ok: true };
});

// Desktop notifications, requested by the injected page script when a reply arrives
// while the window is in the background.
ipcMain.on('sentinel-notify', (e, msg) => {
  if (!Notification.isSupported()) {
    console.warn('[notify] notifications are not supported on this system');
    return;
  }
  const title = String((msg && msg.title) || 'Sentinel').slice(0, 80);
  new Notification({
    title,
    body: String((msg && msg.body) || '').slice(0, 200),
    icon: ICON_PATH,
  }).show();
  console.log('[notify] shown:', title);
});

// Adds desktop-only behaviour to the Sentinel page (see ui-inject.js).
function injectUIExtras(win) {
  // Messages from ui-inject.js come back here so they show up in the launch log.
  win.webContents.on('console-message', (e, level, message) => {
    if (message.startsWith('[sentinel]')) console.log(message);
  });
  win.webContents.on('did-finish-load', () => {
    if (!win.webContents.getURL().startsWith(UI_URL)) return;
    const js = fs.readFileSync(path.join(__dirname, 'ui-inject.js'), 'utf8');
    win.webContents.executeJavaScript(js).catch(err => console.error('[ui-inject]', err.message));
  });
}


// ── BACKEND WATCH ──
// If the backend stops while the window is open, show the connecting/offline page.
// When it comes back, that page moves on to the UI again.
let backendUp = null; // null = not checked yet

function probeBackend(cb) {
  const req = http.get(BACKEND_URL, res => { res.resume(); cb(true); });
  req.on('error', () => cb(false));
  req.setTimeout(2500, () => { req.destroy(); cb(false); });
}

function watchBackend() {
  setInterval(() => {
    probeBackend(up => {
      const wasUp = backendUp;
      backendUp = up;
      if (!up && wasUp === true && mainWindow) {
        console.warn('[backend] went offline; showing the connecting page');
        loadConnecting();
      }
    });
  }, 3000);
}


// Ollama is the system unit ollama.service (loopback only). Only report on it here.
function checkOllama() {
  http.get(OLLAMA_URL, res => {
    res.resume();
    console.log('[Ollama] running on localhost:11434');
  }).on('error', () => {
    console.warn('[Ollama] not reachable on localhost:11434. Start it with: sudo systemctl start ollama');
  }).end();
}

// ── PICK MONITOR ──
// Remembered monitor: the monitor Sentinel was on when it was last hidden or quit.
// Stored as the monitor's bounds (Electron display ids can change across reboots).
const WINDOW_STATE_FILE = path.join(HOME, '.config/sentinel/window.json');

function loadRememberedBounds() {
  try {
    const b = JSON.parse(fs.readFileSync(WINDOW_STATE_FILE, 'utf8'));
    if ([b.x, b.y, b.width, b.height].every(n => Number.isFinite(n))) return b;
  } catch (err) { /* no saved monitor yet */ }
  return null;
}

function rememberCurrentMonitor() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  try {
    const { bounds } = screen.getDisplayMatching(mainWindow.getBounds());
    fs.mkdirSync(path.dirname(WINDOW_STATE_FILE), { recursive: true });
    fs.writeFileSync(WINDOW_STATE_FILE, JSON.stringify(bounds) + '\n');
  } catch (err) {
    console.warn('[monitor] could not remember the monitor:', err.message);
  }
}

// SENTINEL_MONITOR (if set) always wins: right | left | primary | 1,2,3... (left to right)
// Otherwise: the remembered monitor, if it is still connected, else the right-most one.
function pickDisplay() {
  const all = screen.getAllDisplays();
  const byX = [...all].sort((a, b) => a.bounds.x - b.bounds.x);
  const override = process.env.SENTINEL_MONITOR ? process.env.SENTINEL_MONITOR.toLowerCase() : null;

  if (!override) {
    const saved = loadRememberedBounds();
    if (saved) {
      const match = all.find(d => d.bounds.x === saved.x && d.bounds.y === saved.y &&
        d.bounds.width === saved.width && d.bounds.height === saved.height);
      if (match) return match;
      console.warn('[monitor] remembered monitor is not connected; using the default');
    }
  }

  const want = override || 'right';
  if (want === 'primary') return screen.getPrimaryDisplay();
  if (want === 'left') return byX[0];
  if (/^\d+$/.test(want) && byX[Number(want) - 1]) return byX[Number(want) - 1];
  return byX[byX.length - 1];
}

// Make the window fullscreen on the target monitor (unless SENTINEL_WINDOWED is set).
// Electron's fullscreen flag can say "on" before the window manager has applied it, and then a
// plain request does nothing. Leaving fullscreen and re-entering it forces the window manager to act.
function placeOnTarget() {
  if (!mainWindow || mainWindow.isDestroyed() || process.env.SENTINEL_WINDOWED) return;
  mainWindow.setFullScreen(false);
  setTimeout(() => {
    if (mainWindow && !mainWindow.isDestroyed()) mainWindow.setFullScreen(true);
  }, 200);
}

// ── CREATE WINDOW ──
// The connecting page waits for the backend, then moves on to the UI.
// If the backend is down it shows the offline page with a retry.
function loadConnecting() {
  if (!mainWindow) return;
  mainWindow.loadFile(path.join(__dirname, 'connecting.html'), {
    query: { target: UI_URL, backend: BACKEND_URL },
  });
}

function createWindow() {
  // Grant mic and media permissions automatically
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

  // The window opens on a connecting page. It moves on to the UI once the backend answers,
  // or stays on an offline page with a retry if the services are down.
  injectUIExtras(mainWindow);
  loadConnecting();

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    // On a fresh boot the monitors can still be settling, so wait a moment before going fullscreen.
    setTimeout(placeOnTarget, 1500);
    if (!process.env.SENTINEL_QUIET) mainWindow.webContents.openDevTools({ mode: 'detach' });
  });

  // F11 toggles fullscreen
  mainWindow.webContents.on('before-input-event', (e, input) => {
    if (input.type === 'keyDown' && input.key === 'F11') {
      mainWindow.setFullScreen(!mainWindow.isFullScreen());
      e.preventDefault();
    }
  });

  // Closing the window hides it to the tray; Sentinel keeps running.
  mainWindow.on('close', e => {
    e.preventDefault();
    mainWindow.hide();
  });

  // Remember which monitor Sentinel was on whenever it is hidden (close or tray Hide).
  mainWindow.on('hide', rememberCurrentMonitor);

  mainWindow.on('closed', () => { mainWindow = null; });
}

// ── TRAY ──
function createTray() {
  const icon = nativeImage.createFromPath(ICON_PATH).resize({ width: 22, height: 22 });
  tray = new Tray(icon);

  const menu = Menu.buildFromTemplate([
    { label: 'Sentinel V2', enabled: false },
    { type: 'separator' },
    { label: 'Show', click: () => { if (mainWindow) mainWindow.show(); } },
    { label: 'Hide', click: () => { if (mainWindow) mainWindow.hide(); } },
    { type: 'separator' },
    { label: 'Restart services', click: restartServices },
    { label: 'Stop services', click: stopServices },
    { type: 'separator' },
    // Quitting stops the services too (phone and desktop commands stop with it).
    { label: 'Quit Sentinel (stops services)', click: quitSentinel },
  ]);

  tray.setToolTip('Sentinel V2');
  tray.setContextMenu(menu);
  tray.on('click', () => { if (mainWindow) mainWindow.isVisible() ? mainWindow.hide() : mainWindow.show(); });
}

// Quit: stop the services first (synchronously), then exit.
function quitSentinel() {
  rememberCurrentMonitor();
  userctlSync(['stop', ...SERVICES]);
  app.exit(0);
}

// Only one Sentinel window at a time: a second launch just brings the first one forward.
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) { mainWindow.show(); mainWindow.focus(); }
  });
}

// ── APP LIFECYCLE ──
app.whenReady().then(() => {
  app.setName('Sentinel V2');
  // Ties the window to its launcher (SentinelV2.desktop) so the taskbar shows the right icon.
  try { app.setDesktopName('SentinelV2.desktop'); } catch (e) {}
  // Set app icon for Linux taskbar
  try { app.setIcon(nativeImage.createFromPath(ICON_PATH)); } catch (e) {}
  startServices();
  checkOllama();
  watchBackend();
  createWindow();
  createTray();
  // A monitor plugged in, unplugged, or re-sized (common right after boot) re-applies the placement.
  screen.on('display-added', () => placeOnTarget());
  screen.on('display-metrics-changed', () => placeOnTarget());
});

app.on('window-all-closed', e => e.preventDefault()); // Keep running in tray

app.on('activate', () => { if (mainWindow) mainWindow.show(); });
