// sessionFlow.test.js — TICKET-VSC-1B pure flow logic
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const {
  applySessionResult,
  resolveAskGate,
  buildSelectionPayload,
} = require('../out/sessionFlow.js');

test('applySessionResult: 无 panel 时 sessionId 仍被保存（Bug 2 修复核心）', () => {
  const state = { sessionId: null };
  let panelCalled = false;
  const sid = applySessionResult(state, 'sid-1', null);
  assert.strictEqual(sid, 'sid-1');
  assert.strictEqual(state.sessionId, 'sid-1');
  assert.strictEqual(panelCalled, false);
});

test('applySessionResult: 有 panel 时同时回调 setSession', () => {
  const state = { sessionId: null };
  const calls = [];
  applySessionResult(state, 'sid-2', (s) => calls.push(s));
  assert.strictEqual(state.sessionId, 'sid-2');
  assert.deepStrictEqual(calls, ['sid-2']);
});

test('applySessionResult: sid 为空时不污染 state', () => {
  const state = { sessionId: null };
  const sid = applySessionResult(state, undefined, null);
  assert.strictEqual(sid, null);
  assert.strictEqual(state.sessionId, null);
});

test('resolveAskGate: 未连接 → not_connected；已连无 sid → connecting；都就绪 → ok', () => {
  assert.deepStrictEqual(resolveAskGate(false, null), { kind: 'not_connected' });
  assert.deepStrictEqual(resolveAskGate(false, 'sid'), { kind: 'not_connected' });
  assert.deepStrictEqual(resolveAskGate(true, null), { kind: 'connecting' });
  assert.deepStrictEqual(resolveAskGate(true, 'sid'), { kind: 'ok' });
});

test('buildSelectionPayload: 非空选区产出 payload，行号 1-based', () => {
  const p = buildSelectionPayload('src/a.ts', 3, 5, 'const x = 1;\nconst y = 2;');
  assert.deepStrictEqual(p, {
    filePath: 'src/a.ts',
    startLine: 3,
    endLine: 5,
    text: 'const x = 1;\nconst y = 2;',
  });
});

test('buildSelectionPayload: 空选区/空文本 → null（不发）', () => {
  assert.strictEqual(buildSelectionPayload('a.ts', 1, 1, ''), null);
  assert.strictEqual(buildSelectionPayload('a.ts', 1, 1, '   \n  '), null);
});

test('buildSelectionPayload: text 截断到 500 字符', () => {
  const long = 'x'.repeat(600);
  const p = buildSelectionPayload('a.ts', 1, 1, long);
  assert.ok(p);
  assert.strictEqual(p.text.length, 500);
});
