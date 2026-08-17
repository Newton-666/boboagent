// protocol.test.js — frame encode/parse (TICKET-VSC-1)
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const {
  parseLine, encodeRequest, encodeResponse, encodeEvent, isEvent, isResponse,
} = require('../out/protocol.js');

test('encodeRequest produces one JSON line + newline', () => {
  const line = encodeRequest('prompt.submit', { session_id: 's1', text: 'hi' }, 7);
  assert.ok(line.endsWith('\n'));
  const obj = JSON.parse(line.trim());
  assert.strictEqual(obj.jsonrpc, '2.0');
  assert.strictEqual(obj.method, 'prompt.submit');
  assert.strictEqual(obj.id, 7);
  assert.strictEqual(obj.params.text, 'hi');
});

test('parseLine round-trips a request', () => {
  const line = encodeRequest('session.create', { title: 'x' }, 1);
  const m = parseLine(line);
  assert.ok(m && m.method === 'session.create');
  assert.strictEqual(m.id, 1);
});

test('parseLine detects events and responses', () => {
  const ev = parseLine(encodeEvent('message.delta', { session_id: 's1', text: 'a' }));
  assert.ok(isEvent(ev));
  assert.ok(!isResponse(ev));
  assert.strictEqual(ev.params.type, 'message.delta');

  const resp = parseLine(encodeResponse(3, { ok: true }));
  assert.ok(isResponse(resp));
  assert.ok(!isEvent(resp));
  assert.deepStrictEqual(resp.result, { ok: true });

  const errResp = parseLine(encodeResponse(4, undefined, { code: -32000, message: 'no' }));
  assert.ok(isResponse(errResp));
  assert.strictEqual(errResp.error.code, -32000);
});

test('parseLine handles blank lines and bad JSON gracefully', () => {
  assert.strictEqual(parseLine(''), null);
  assert.strictEqual(parseLine('  \n'), null);
  assert.strictEqual(parseLine('not json'), null);
});

test('unicode survives the line protocol (ensure_ascii=false equivalent)', () => {
  const line = encodeRequest('prompt.submit', { text: '解释这段代码：为什么这里用生成器？' }, 9);
  const obj = JSON.parse(line.trim());
  assert.strictEqual(obj.params.text, '解释这段代码：为什么这里用生成器？');
});
