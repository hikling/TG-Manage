'use strict';

// Exercise a real upstream message listener through the same TypeScript loader
// as the per-account worker, without connecting to Telegram.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

async function main() {
  const filename = path.join(process.cwd(), 'assets', 'kitt', 'kitt_config.json');
  const previous = fs.existsSync(filename) ? fs.readFileSync(filename) : null;
  fs.mkdirSync(path.dirname(filename), { recursive: true });
  fs.writeFileSync(filename, JSON.stringify({
    index: '1',
    tasks: [{ id: '1', remark: 'integration smoke', status: '1',
      match: "return msg.message === 'integration-smoke'",
      action: 'globalThis.__signpulseKittAction = (globalThis.__signpulseKittAction || 0) + 1',
    }],
  }));
  try {
    const plugin = require('../src/plugin/kitt.ts').default;
    await plugin.listenMessageHandler({ message: 'integration-smoke', client: null });
    assert.equal(globalThis.__signpulseKittAction, 1, 'matched plugin must execute its action');
  } finally {
    if (previous) fs.writeFileSync(filename, previous);
    else fs.unlinkSync(filename);
    delete globalThis.__signpulseKittAction;
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
