// Drives one page in a headless Chromium over the DevTools protocol, on the
// real clock, and writes what the page logged.
//
//   node runner.js URL --out PREFIX [--wait MS] [--width W] [--height H]
//        [--dsf N] [--shot-scale N] [--inject FILE] [--virtual MS]
//        [--coverage URL_PREFIX] [--motion] [--browser PATH] [--profile DIR]
//        [--clip JS]...
//
// The run ends when the page sets window.__log.done, or after --wait of wall
// clock. window.__log goes to PREFIX.json; each --clip expression (JS
// returning {x, y, width, height} in page coordinates) is captured as
// PREFIX_<n>.png. --coverage records which style rules and functions of the
// files under URL_PREFIX ran, into PREFIX.coverage.json. --profile hands the
// browser profile's folder to a caller that outlives this process and
// removes it; otherwise one is made here and removed at the end. Needs
// Node 22+ (native WebSocket and fetch).
//
// Why the real clock: a virtual-time budget fast-forwards whenever the page is
// idle, so anything paced by timers against a real backend runs out its
// schedule in well under a second and reports a state no reader ever sees.
const { spawn, spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { parseArgs } = require('node:util');

const { values: options, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    out: { type: 'string' },
    wait: { type: 'string', default: '30000' },
    width: { type: 'string', default: '1280' },
    height: { type: 'string', default: '1400' },
    dsf: { type: 'string', default: '1' },
    'shot-scale': { type: 'string', default: '2' },
    inject: { type: 'string' },
    virtual: { type: 'string', default: '0' },
    coverage: { type: 'string' },
    motion: { type: 'boolean', default: false },
    browser: { type: 'string', default: process.env.PRUMO_BROWSER },
    profile: { type: 'string' },
    clip: { type: 'string', multiple: true, default: [] },
  },
});
const [url] = positionals;
if (!url || !options.out) {
  console.log('error: usage: node runner.js URL --out PREFIX [options]');
  process.exit(1);
}

const INSTALLED = {
  win32: [
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  ],
  linux: ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/microsoft-edge'],
  darwin: [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  ],
};
const BROWSER = options.browser || (INSTALLED[process.platform] || []).find((candidate) => fs.existsSync(candidate));
if (!BROWSER || !fs.existsSync(BROWSER)) {
  console.log(
    BROWSER
      ? `error: the browser points to nothing: ${BROWSER}`
      : 'error: no Chromium browser found; pass --browser or set PRUMO_BROWSER',
  );
  process.exit(1);
}
const owned = !options.profile;
const profile = options.profile || fs.mkdtempSync(path.join(os.tmpdir(), 'prumo-'));

const child = spawn(
  BROWSER,
  [
    '--headless=new',
    '--disable-gpu',
    '--hide-scrollbars',
    // Settled states by default; --motion keeps transitions, to measure one.
    ...(options.motion ? [] : ['--force-prefers-reduced-motion']),
    // Port 0: the browser picks a free port and writes it to DevToolsActivePort
    // in the profile. A fixed port can attach to a previous run's instance that
    // is still shutting down.
    '--window-size=1280,1400',
    '--remote-debugging-port=0',
    `--user-data-dir=${profile}`,
    // CI runners on recent Ubuntu block the unprivileged user namespaces
    // Chrome's sandbox needs; the page under test is the project's own.
    ...(process.env.CI ? ['--no-sandbox'] : []),
    'about:blank',
  ],
  { stdio: 'ignore' },
);
// Unhandled, a failed launch kills this process before the profile is
// removed; handled, the run waits out its ceiling and cleans up as usual.
child.on('error', (error) => console.log('error: the browser did not start: ' + error.message));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Keys a scenario can press: name -> [key, code, virtual key code, text].
const KEYS = {
  Tab: ['Tab', 'Tab', 9, ''],
  Enter: ['Enter', 'Enter', 13, '\r'],
  Escape: ['Escape', 'Escape', 27, ''],
  Space: [' ', 'Space', 32, ' '],
  ArrowDown: ['ArrowDown', 'ArrowDown', 40, ''],
  ArrowUp: ['ArrowUp', 'ArrowUp', 38, ''],
};

// "Shift+Tab" style names add modifiers (Alt 1, Ctrl 2, Meta 4, Shift 8).
async function press(send, name) {
  const parts = String(name).split('+');
  const spec = KEYS[parts.pop()];
  if (!spec) return;
  const modifiers = parts.reduce((m, p) => m | ({ Alt: 1, Ctrl: 2, Meta: 4, Shift: 8 }[p] || 0), 0);
  const [key, code, keyCode, text] = spec;
  const base = { key, code, windowsVirtualKeyCode: keyCode, nativeVirtualKeyCode: keyCode, modifiers };
  await send('Input.dispatchKeyEvent', { type: text ? 'keyDown' : 'rawKeyDown', text, ...base });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', ...base });
}

// The pointer moved onto the centre of the first element the selector matches.
async function hover(send, evaluate, selector) {
  const point = await evaluate(`(function () {
    var element = document.querySelector(${JSON.stringify(selector)});
    if (!element) return null;
    var box = element.getBoundingClientRect();
    return { x: box.left + box.width / 2, y: box.top + box.height / 2 };
  })()`);
  if (point) await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: point.x, y: point.y });
}

// A ceiling, not a delay: under load (parallel runs, a JVM starting) the
// browser can take well over ten seconds to write DevToolsActivePort.
async function target() {
  for (let i = 0; i < 150; i++) {
    try {
      const port = fs.readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').split(/\r?\n/)[0].trim();
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const page = list.find((t) => t.type === 'page');
      if (page) return { ws: page.webSocketDebuggerUrl, port };
    } catch {
      /* not up yet */
    }
    await sleep(200);
  }
  throw new Error('DevTools endpoint never came up');
}

/*
 * On Windows the launched executable hands off to the real browser process
 * and exits, so killing its process tree kills nothing and leaks a browser
 * and a profile per run. The browser is closed over the protocol, the
 * profile removed with retries while Windows releases its files, and only
 * as a last resort are the processes holding this run's profile killed.
 * Under load Windows can hold the files for longer than any retry here, so
 * a profile handed in with --profile is left to the caller, which outlives
 * this process and keeps trying.
 */
async function shutdown(port) {
  try {
    if (port) {
      const version = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
      const browser = new WebSocket(version.webSocketDebuggerUrl);
      await new Promise((resolve, reject) => {
        browser.addEventListener('open', resolve, { once: true });
        browser.addEventListener('error', reject, { once: true });
      });
      browser.send(JSON.stringify({ id: 1, method: 'Browser.close' }));
      await sleep(300);
    }
  } catch {
    /* the forceful path below still runs */
  }
  // A browser that never became controllable may still be starting, and would
  // recreate the profile after it was removed, so it is killed first.
  if (!port) killProfileProcesses();
  if (!owned) return;
  for (let i = 0; i < 20; i++) {
    try {
      fs.rmSync(profile, { recursive: true, force: true });
      break;
    } catch {
      await sleep(250);
    }
  }
  if (fs.existsSync(profile)) {
    killProfileProcesses();
    try {
      fs.rmSync(profile, { recursive: true, force: true });
    } catch {
      /* reported below */
    }
  }
  if (!port) await sleep(1000);
  if (fs.existsSync(profile)) {
    killProfileProcesses();
    try {
      fs.rmSync(profile, { recursive: true, force: true });
    } catch {
      console.log('error: profile left behind at ' + profile);
    }
  }
}

// Only the processes started with this run's profile, whatever the browser.
function killProfileProcesses() {
  if (process.platform === 'win32') {
    spawnSync('powershell', [
      '-NoProfile',
      '-Command',
      `Get-CimInstance Win32_Process -Filter "Name='${path.basename(BROWSER)}'" | Where-Object { $_.CommandLine -like '*${profile}*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }`,
    ]);
  } else {
    child.kill('SIGKILL');
    spawnSync('pkill', ['-KILL', '-f', profile]);
  }
}

// The file under --coverage a URL serves, or null for anything else: other
// origins, the page's own documents and Prumo's own files.
function shipped(sourceUrl) {
  if (!options.coverage || !sourceUrl) return null;
  const clean = sourceUrl.split(/[?#]/)[0];
  if (!clean.startsWith(options.coverage)) return null;
  const file = clean.slice(options.coverage.length);
  return file && !path.posix.basename(file).startsWith('prumo-') ? file : null;
}

(async () => {
  let ws;
  let port;
  try {
    const endpoint = await target();
    port = endpoint.port;
    ws = new WebSocket(endpoint.ws);
    await new Promise((r) => ws.addEventListener('open', r, { once: true }));
    let id = 0;
    const pending = new Map();
    const events = new Map();
    const stylesheets = new Map();
    ws.addEventListener('message', (m) => {
      const msg = JSON.parse(m.data);
      if (msg.id && pending.has(msg.id)) {
        pending.get(msg.id)(msg);
        pending.delete(msg.id);
      }
      if (msg.method && events.has(msg.method)) {
        events.get(msg.method)(msg);
        events.delete(msg.method);
      }
      if (msg.method === 'CSS.styleSheetAdded')
        stylesheets.set(msg.params.header.styleSheetId, msg.params.header.sourceURL);
    });
    const send = (method, params = {}) =>
      new Promise((r) => {
        const n = ++id;
        pending.set(n, r);
        ws.send(JSON.stringify({ id: n, method, params }));
      });
    const evaluate = async (expression) =>
      (await send('Runtime.evaluate', { expression, returnByValue: true })).result.result.value;

    await send('Page.enable');
    // --inject runs a script at the start of every document, so a page that
    // does not load Prumo itself can still be measured: a site as it is
    // served, or a reference page opened from disk.
    if (options.inject) {
      await send('Page.addScriptToEvaluateOnNewDocument', { source: fs.readFileSync(options.inject, 'utf8') });
    }
    // --window-size is not honoured for a page opened over the protocol, so
    // the viewport is set here.
    await send('Emulation.setDeviceMetricsOverride', {
      width: Number(options.width),
      height: Number(options.height),
      deviceScaleFactor: Number(options.dsf),
      mobile: false,
    });
    // A headless page does not always hold the window's focus, and keys sent
    // to an unfocused page go nowhere. This makes the page behave as focused.
    await send('Emulation.setFocusEmulationEnabled', { enabled: true });
    // The same tracking the DevTools Coverage panel uses: code no scenario
    // reaches is code no check can protect.
    if (options.coverage) {
      await send('DOM.enable');
      await send('CSS.enable');
      await send('CSS.startRuleUsageTracking');
      await send('Profiler.enable');
      await send('Profiler.startPreciseCoverage', { callCount: true, detailed: true });
    }
    // Virtual time: the clock is paused until the page has started loading,
    // then runs on a budget that stops for network fetches. Fast for long idle
    // scenarios, but idle time is skipped and animation frames are starved,
    // so it cannot judge anything paced by time.
    const virtual = Number(options.virtual);
    if (virtual) {
      await send('Emulation.setVirtualTimePolicy', { policy: 'pause' });
      await send('Page.navigate', { url });
      const expired = new Promise((r) => events.set('Emulation.virtualTimeBudgetExpired', r));
      await send('Emulation.setVirtualTimePolicy', { policy: 'pauseIfNetworkFetchesPending', budget: virtual });
      // The budget-expired event does not always arrive; the log is read either
      // way, so a missed event costs a little wall clock, never the result.
      await Promise.race([expired, sleep(virtual + 20000)]);
    } else {
      await send('Page.navigate', { url });
      // While waiting, deliver the input the page asked for (V.press, V.hover)
      // as real, trusted events. Synthetic events from inside the page are
      // untrusted: Chromium shows :focus-visible only after real keyboard
      // input, and :hover only follows a real pointer.
      const end = Date.now() + Number(options.wait);
      while (Date.now() < end) {
        const inputs = await evaluate('(window.__prumoInput || []).splice(0)');
        for (const input of inputs || []) {
          if (input && input.hover) await hover(send, evaluate, input.hover);
          else await press(send, input);
        }
        if (await evaluate('!!(window.__log && window.__log.done)')) break;
        await sleep(40);
      }
    }

    // A page with no log says where it ended up, so the cause can be read off
    // the result: another URL, a page still loading, a core that never ran.
    const log = await evaluate(`JSON.stringify(window.__log || { checks: [], errors: ['the page produced no log: '
      + JSON.stringify({ at: location.href, readyState: document.readyState, core: typeof window.V === 'object' })] })`);
    fs.writeFileSync(`${options.out}.json`, log || 'null');
    if (options.coverage) {
      // An @import'ed sheet is a sheet of its own, under its own URL.
      const rules = (await send('CSS.stopRuleUsageTracking')).result.ruleUsage
        .map((rule) => [shipped(stylesheets.get(rule.styleSheetId)), rule])
        .filter(([file]) => file)
        .map(([file, rule]) => [file, rule.startOffset, rule.endOffset, rule.used]);
      const functions = (await send('Profiler.takePreciseCoverage')).result.result
        .map((script) => [shipped(script.url), script])
        .filter(([file]) => file && file.endsWith('.js'))
        .flatMap(([file, script]) =>
          script.functions.map((fn) => [
            file,
            fn.functionName,
            fn.ranges[0].startOffset,
            fn.ranges[0].endOffset,
            fn.ranges[0].count,
          ]),
        );
      fs.writeFileSync(`${options.out}.coverage.json`, JSON.stringify({ rules, functions }));
    }
    for (let i = 0; i < options.clip.length; i++) {
      const box = await evaluate(options.clip[i]);
      if (!box) continue;
      const shot = await send('Page.captureScreenshot', {
        format: 'png',
        captureBeyondViewport: true,
        clip: { ...box, scale: Number(options['shot-scale']) },
      });
      fs.writeFileSync(`${options.out}_${i}.png`, Buffer.from(shot.result.data, 'base64'));
    }
    console.log('done');
  } catch (e) {
    console.log('error: ' + e.message);
  } finally {
    if (ws) ws.close();
    await shutdown(port);
  }
})();
