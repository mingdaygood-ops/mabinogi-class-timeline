// Same-origin API fetcher driven through headless Chrome via the DevTools protocol.
//
// Some sites (mabimobi.life) sit behind a bot check that rejects plain HTTP
// clients, so this script opens a real page in headless Chrome and runs fetch()
// inside that page. It speaks JSON lines on stdio so the caller can decide the
// next request from the previous answer while one browser session stays open:
//
//   stdout line 1: {"ready": true, "url": "<final page url>"}
//   stdin  line  : {"path": "/d/api/v1/..."}      (same-origin path only)
//   stdout line  : {"status": 200, "body": "<response text>"} or {"error": "..."}
//
// Closing stdin shuts Chrome down. Any fatal problem is written to stderr and
// the process exits non-zero.
//
// Usage: node cdp_fetch.mjs --url https://mabimobi.life/ranking/nightmare
//          [--chrome /opt/google/chrome/chrome] [--interval-ms 1000]
//          [--path-prefix /d/api/] [--load-timeout-ms 60000]

import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import readline from 'node:readline';

const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36';

function parseArgs(argv) {
  const opts = {
    url: null,
    chrome: '/opt/google/chrome/chrome',
    intervalMs: 1000,
    pathPrefix: '/d/api/',
    loadTimeoutMs: 60000,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const v = argv[i + 1];
    if (a === '--url') opts.url = v;
    else if (a === '--chrome') opts.chrome = v;
    else if (a === '--interval-ms') opts.intervalMs = Number(v);
    else if (a === '--path-prefix') opts.pathPrefix = v;
    else if (a === '--load-timeout-ms') opts.loadTimeoutMs = Number(v);
    else throw new Error(`unknown argument: ${a}`);
    i++;
  }
  if (!opts.url) throw new Error('--url is required');
  return opts;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function fail(msg) {
  process.stderr.write(`cdp_fetch: ${msg}\n`);
  cleanup();
  process.exit(1);
}

let chrome = null;
let profileDir = null;
let ws = null;

function cleanup() {
  try {
    if (ws) ws.close();
  } catch {}
  try {
    if (chrome && chrome.exitCode === null) chrome.kill('SIGKILL');
  } catch {}
  if (profileDir) {
    try {
      fs.rmSync(profileDir, { recursive: true, force: true });
    } catch {}
  }
}

process.on('SIGINT', () => fail('interrupted'));
process.on('SIGTERM', () => fail('terminated'));

async function waitForPageTarget(port, deadline) {
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`http://127.0.0.1:${port}/json`);
      const targets = await res.json();
      const page = targets.find((t) => t.type === 'page');
      if (page) return page;
    } catch {}
    await sleep(200);
  }
  throw new Error('Chrome DevTools endpoint did not come up');
}

function connect(wsUrl) {
  return new Promise((resolve, reject) => {
    const sock = new WebSocket(wsUrl);
    let nextId = 0;
    const pending = new Map();
    const listeners = new Set();
    sock.addEventListener('message', (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id && pending.has(msg.id)) {
        pending.get(msg.id)(msg);
        pending.delete(msg.id);
      } else if (msg.method) {
        for (const fn of listeners) fn(msg);
      }
    });
    sock.addEventListener('error', () => reject(new Error('DevTools websocket error')));
    sock.addEventListener('close', () => {
      for (const fn of pending.values()) fn({ error: { message: 'websocket closed' } });
      pending.clear();
    });
    sock.addEventListener('open', () => {
      const send = (method, params = {}) =>
        new Promise((r) => {
          const id = ++nextId;
          pending.set(id, r);
          sock.send(JSON.stringify({ id, method, params }));
        });
      resolve({ sock, send, listeners });
    });
  });
}

async function evaluate(send, expression, timeoutMs) {
  const res = await send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
    timeout: timeoutMs,
  });
  if (res.error) throw new Error(`Runtime.evaluate failed: ${res.error.message}`);
  if (res.result.exceptionDetails) {
    const d = res.result.exceptionDetails;
    throw new Error(`page exception: ${d.exception?.description || d.text}`);
  }
  return res.result.result.value;
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  const origin = new URL(opts.url).origin;
  profileDir = fs.mkdtempSync(path.join(os.tmpdir(), 'cdp-fetch-'));
  const port = 9300 + Math.floor(Math.random() * 600);
  const args = [
    '--headless=new',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    `--user-agent=${UA}`,
    '--lang=ko-KR',
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profileDir}`,
    '--window-size=1400,1000',
    'about:blank',
  ];
  // Chrome refuses to start as root unless the sandbox is disabled.
  if (typeof process.getuid === 'function' && process.getuid() === 0) args.unshift('--no-sandbox');
  chrome = spawn(opts.chrome, args, { stdio: 'ignore' });
  chrome.on('error', (e) => fail(`cannot start Chrome at ${opts.chrome}: ${e.message}`));
  chrome.on('exit', (code) => {
    if (code !== null && code !== 0) fail(`Chrome exited with code ${code}`);
  });

  const deadline = Date.now() + opts.loadTimeoutMs;
  const target = await waitForPageTarget(port, deadline);
  const cdp = await connect(target.webSocketDebuggerUrl);
  ws = cdp.sock;
  const { send } = cdp;
  await send('Page.enable');
  await send('Runtime.enable');
  const nav = await send('Page.navigate', { url: opts.url });
  if (nav.error || nav.result?.errorText) {
    throw new Error(`navigation failed: ${nav.error?.message || nav.result.errorText}`);
  }

  // Wait until the document is complete on the target origin and no longer shows
  // a bot-check interstitial (its title typically says "Just a moment").
  let ready = false;
  while (Date.now() < deadline) {
    await sleep(1000);
    let state;
    try {
      state = await evaluate(
        send,
        '({ ready: document.readyState, origin: location.origin, title: document.title, href: location.href })',
        5000,
      );
    } catch {
      continue;
    }
    if (
      state &&
      state.ready === 'complete' &&
      state.origin === origin &&
      !/just a moment|attention required|checking your browser/i.test(state.title)
    ) {
      ready = true;
      process.stdout.write(JSON.stringify({ ready: true, url: state.href }) + '\n');
      break;
    }
  }
  if (!ready) throw new Error(`page did not finish loading within ${opts.loadTimeoutMs} ms`);
  // Give the page's own scripts a moment to settle any cookies they set.
  await sleep(2000);

  const rl = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
  let last = 0;
  for await (const line of rl) {
    if (!line.trim()) continue;
    let req;
    try {
      req = JSON.parse(line);
    } catch {
      process.stdout.write(JSON.stringify({ error: 'request line is not JSON' }) + '\n');
      continue;
    }
    const p = req.path;
    if (typeof p !== 'string' || !p.startsWith(opts.pathPrefix)) {
      process.stdout.write(
        JSON.stringify({ error: `path must be a string starting with ${opts.pathPrefix}` }) + '\n',
      );
      continue;
    }
    const wait = last + opts.intervalMs - Date.now();
    if (wait > 0) await sleep(wait);
    last = Date.now();
    const expr =
      `fetch(${JSON.stringify(p)}, { credentials: 'include', headers: { Accept: 'application/json' } })` +
      '.then(async (r) => ({ status: r.status, body: await r.text() }))' +
      '.catch((e) => ({ error: String(e) }))';
    let out;
    try {
      out = await evaluate(send, expr, 60000);
    } catch (e) {
      out = { error: e.message };
    }
    process.stdout.write(JSON.stringify(out ?? { error: 'empty evaluation result' }) + '\n');
  }
  cleanup();
  process.exit(0);
}

main().catch((e) => fail(e.message));
