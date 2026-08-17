/**
 * e2e-gateway.js — TICKET-VSC-1 protocol-level live test against a REAL bobo
 * gateway in socket mode. Not part of `npm test` (needs a running gateway +
 * API key); run manually:
 *
 *   cd apps/vscode-extension
 *   node test/e2e-gateway.js <sockPath>
 *
 * Verifies the full ask-chain the extension uses:
 *   session.create -> prompt.submit (Explain OFF) -> stream delta -> complete
 *   -> prompt.submit (Explain ON)  -> stream delta -> complete
 *
 * Screenshot-equivalent evidence: prints the live reply bodies and saves
 * them to out/e2e-live-<ts>.txt.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const os = require('os');
const { SocketClient } = require('../out/socketClient.js');

const sockPath = process.argv[2] || path.join(os.tmpdir(), 'bobo-gw-e2e.sock');

const SELECTION_CTX = [
  'File: src/demo.py (python)',
  'Lines: 3-6',
  '```python',
  'def fib(n):',
  '    return n if n < 2 else fib(n - 1) + fib(n - 2)',
  '```',
].join('\n');

const QUESTION = 'Explain this code.';
const EXPLAIN_OFF = `Answer the question directly and concisely.\n\n---\n\n${SELECTION_CTX}\n\n${QUESTION}`;
const EXPLAIN_ON = `You are in EXPLAIN mode — teach, do not just answer.\nExplain the concept first (what it is, in plain words), then why this code is written this way,\nthen walk through the selected code step by step. Give further-reading pointers at the end.\nExplain in Chinese; keep any code snippets and comments in their original language.\n\n---\n\n${SELECTION_CTX}\n\n${QUESTION}`;

function ask(client, sid, label, text, out) {
  return new Promise((resolve, reject) => {
    let streamed = '';
    const timer = setTimeout(() => reject(new Error(`${label}: timeout waiting for message.complete`)), 120000);
    const evHandler = (ev) => {
      const p = ev.params || {};
      const payload = p.payload || {};
      const merged = { ...p, ...payload };
      const t = merged.type || '';
      if (t === 'message.delta' && typeof merged.text === 'string') {
        streamed += merged.text;
        process.stdout.write('.');
      } else if (t === 'message.complete') {
        clearTimeout(timer);
        client.onEvent = null;
        const final = String(merged.final_text || '');
        out.push(`=== ${label} ===`);
        out.push(`[delta-streamed ${streamed.length} chars]`);
        out.push(`[final_text ${final.length} chars]`);
        out.push('--- final_text (first 400) ---');
        out.push(final.slice(0, 400));
        out.push('');
        console.log(`\n${label}: streamed ${streamed.length} chars, final ${final.length} chars`);
        resolve();
      }
    };
    client.onEvent = evHandler;
    client.send('prompt.submit', { session_id: sid, text }).catch(reject);
  });
}

async function main() {
  if (!fs.existsSync(sockPath)) {
    console.error(`socket not found: ${sockPath}\nStart the gateway first:\n  BOBO_GW_SOCKET=${sockPath} python -m bobo_tui_gateway.entry`);
    process.exit(2);
  }
  const client = new SocketClient({ backoffMs: 300, maxBackoffMs: 2000, jitter: 0 });
  await new Promise((resolve, reject) => {
    client.onConnect = resolve;
    client.onDisconnect = (e) => { if (e) reject(e); };
    client.connect(sockPath);
  });
  console.log(`connected to ${sockPath}`);

  const r = await client.send('session.create', {});
  const sid = r && r.session_id;
  if (!sid) throw new Error(`session.create failed: ${JSON.stringify(r)}`);
  console.log(`session: ${sid}`);

  const out = [`bobo gateway live test (socket=${sockPath})`, `session=${sid}`, `time=${new Date().toISOString()}`, ''];
  await ask(client, sid, 'Explain OFF', EXPLAIN_OFF, out);
  await ask(client, sid, 'Explain ON', EXPLAIN_ON, out);

  const fname = path.join(__dirname, '..', 'out', `e2e-live-${Date.now()}.txt`);
  fs.writeFileSync(fname, out.join('\n'));
  console.log(`\nevidence saved: ${fname}`);
  client.close();
  process.exit(0);
}

main().catch((e) => { console.error('\nE2E FAILED:', e.message); process.exit(1); });
