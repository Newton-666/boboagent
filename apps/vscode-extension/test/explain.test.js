// explain.test.js — Explain-mode prefix (TICKET-VSC-1)
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { buildPrompt, EXPLAIN_PREFIX, DIRECT_PREFIX, hasExplainDirective } = require('../out/explain.js');

test('explain prefix teaches concepts first, Chinese, code comments stay original', () => {
  assert.ok(EXPLAIN_PREFIX.includes('EXPLAIN mode'));
  assert.ok(EXPLAIN_PREFIX.includes('concept'));
  assert.ok(EXPLAIN_PREFIX.includes('why'));
  assert.ok(EXPLAIN_PREFIX.includes('further-reading'));
  assert.ok(EXPLAIN_PREFIX.includes('Chinese'));
  assert.ok(EXPLAIN_PREFIX.includes('original language'));
});

test('direct prefix is a short instruction', () => {
  assert.ok(DIRECT_PREFIX.length < 60);
  assert.ok(DIRECT_PREFIX.includes('directly'));
});

test('buildPrompt prefixes explain directive when on', () => {
  const p = buildPrompt('解释这段代码', true);
  assert.ok(p.startsWith(EXPLAIN_PREFIX));
  assert.ok(p.includes('解释这段代码'));
  const d = buildPrompt('解释这段代码', false);
  assert.ok(d.startsWith(DIRECT_PREFIX));
  assert.ok(!d.includes('EXPLAIN mode'));
});

test('buildPrompt keeps user message intact (no mangling)', () => {
  const user = '```ts\nconst a = 1;\n```\n为什么？';
  const p = buildPrompt(user, true);
  assert.ok(p.endsWith(user));
});

test('hasExplainDirective detects teaching language', () => {
  assert.ok(hasExplainDirective('请解释一下这个函数'));
  assert.ok(hasExplainDirective('讲一讲闭包'));
  assert.ok(hasExplainDirective('为什么这里这么写'));
  assert.ok(!hasExplainDirective('怎么调用这个 API'));
});
