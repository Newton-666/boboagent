// discover.test.js — socket discovery (TICKET-VSC-1)
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { candidateSocketPaths, scanTmpSockets } = require('../out/discover.js');

test('explicit path wins over env, env wins over tmp scan', () => {
  const env = { BOBO_GW_SOCKET: '/tmp/env.sock' };
  const c = candidateSocketPaths('/tmp/explicit.sock', env);
  assert.strictEqual(c[0], '/tmp/explicit.sock');
  assert.ok(c.includes('/tmp/env.sock'));
});

test('scanTmpSockets finds bobo-gw-*.sock and ignores others, newest first', () => {
  const dir = os.tmpdir();
  const a = path.join(dir, 'bobo-gw-1000-1111111111.sock');
  const b = path.join(dir, 'bobo-gw-2000-2222222222.sock');
  const c = path.join(dir, 'unrelated.sock');
  const t1 = path.join(dir, 'bobo-gw-3000-3333333333.sock');
  try {
    for (const p of [a, b, c, t1]) fs.writeFileSync(p, '');
    const found = scanTmpSockets();
    assert.ok(found.includes(a));
    assert.ok(found.includes(b));
    assert.ok(!found.includes(c));
    assert.strictEqual(found[0], t1); // newest mtime first (created last)
  } finally {
    for (const p of [a, b, c, t1]) { try { fs.unlinkSync(p); } catch { /* ignore */ } }
  }
});

test('candidateSocketPaths dedupes', () => {
  const env = { BOBO_GW_SOCKET: '/tmp/x.sock' };
  const c = candidateSocketPaths('/tmp/x.sock', env);
  const count = c.filter((x) => x === '/tmp/x.sock').length;
  assert.strictEqual(count, 1);
});
