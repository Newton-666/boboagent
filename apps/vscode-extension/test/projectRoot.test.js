// projectRoot.test.js — TICKET-VSC-2C：project_root 推导单测（与选区解耦）。
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { resolveProjectRoot } = require('../out/projectRoot.js');

test('有 workspace：project_root 无条件 = workspaceFolders[0].uri.fsPath（不依赖选区）', () => {
  const folders = [
    { uri: { fsPath: '/Users/niuqingwei/Desktop/boboagent_main' } },
    { uri: { fsPath: '/Users/niuqingwei/Desktop/other' } },
  ];
  assert.strictEqual(resolveProjectRoot(folders), '/Users/niuqingwei/Desktop/boboagent_main');
});

test('无 workspace（单文件模式）：project_root = undefined（不抛错）', () => {
  assert.strictEqual(resolveProjectRoot(undefined), undefined);
});

test('workspaceFolders 为空数组：project_root = undefined', () => {
  assert.strictEqual(resolveProjectRoot([]), undefined);
});
