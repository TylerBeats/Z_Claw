const fs = require('fs');
const net = require('net');
const path = require('path');
const { spawn } = require('child_process');

const GATEWAY_HOST = '127.0.0.1';
const GATEWAY_PORT = 18789;
const RETRY_MS = 5000;
const IDLE_POLL_MS = 30000;

function gatewayModulePath() {
  const candidates = [
    process.env.OPENCLAW_MODULE_PATH,
    process.env.APPDATA && path.join(process.env.APPDATA, 'npm', 'node_modules', 'openclaw', 'openclaw.mjs'),
    path.join(__dirname, 'node_modules', 'openclaw', 'openclaw.mjs'),
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }

  return null;
}

function isGatewayRunning() {
  return new Promise((resolve) => {
    const socket = net.connect({ host: GATEWAY_HOST, port: GATEWAY_PORT });
    let settled = false;

    const finish = (value) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(value);
    };

    socket.once('connect', () => finish(true));
    socket.once('error', () => finish(false));
    socket.setTimeout(1500, () => finish(false));
  });
}

async function start() {
  const modulePath = gatewayModulePath();
  if (!modulePath) {
    console.error('[gateway] openclaw.mjs not found. Set OPENCLAW_MODULE_PATH or install OpenClaw globally.');
    setTimeout(start, IDLE_POLL_MS);
    return;
  }

  if (await isGatewayRunning()) {
    console.log(`[gateway] already listening on ${GATEWAY_HOST}:${GATEWAY_PORT}; wrapper idle`);
    setTimeout(start, IDLE_POLL_MS);
    return;
  }

  const proc = spawn(process.execPath, [modulePath, 'gateway', 'run'], {
    stdio: 'inherit',
    shell: false,
  });

  proc.on('exit', async (code) => {
    const running = await isGatewayRunning();
    if (running) {
      console.log(`[gateway] child exited with code ${code}, but another gateway is already running; pausing retries`);
      setTimeout(start, IDLE_POLL_MS);
      return;
    }

    console.log(`[gateway] exited with code ${code}; restarting in ${Math.floor(RETRY_MS / 1000)}s`);
    setTimeout(start, RETRY_MS);
  });
}

start().catch((err) => {
  console.error(`[gateway] wrapper failure: ${err && err.message ? err.message : err}`);
  setTimeout(start, RETRY_MS);
});
