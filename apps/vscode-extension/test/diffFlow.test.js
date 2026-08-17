// diffFlow.test.js — TICKET-VSC-2C diff 协作纯逻辑
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const {
  WRITE_TOOLS,
  extractTargetPath,
  hasInlineDiff,
  SnapshotStore,
  restoreSnapshot,
} = require('../out/diffFlow.js');

test('extractTargetPath: edit_file 取 file_path', () => {
  assert.strictEqual(extractTargetPath('edit_file', { file_path: 'src/a.ts', old_string: 'x' }), 'src/a.ts');
});

test('extractTargetPath: file_operation 取 path', () => {
  assert.strictEqual(extractTargetPath('file_operation', { action: 'write', path: 'b.txt' }), 'b.txt');
});

test('extractTargetPath: 非写文件工具 → null', () => {
  assert.strictEqual(extractTargetPath('web_search', { query: 'x' }), null);
  assert.strictEqual(extractTargetPath('task_ledger', { action: 'list' }), null);
});

test('extractTargetPath: 无路径字段 → null', () => {
  assert.strictEqual(extractTargetPath('edit_file', {}), null);
  assert.strictEqual(extractTargetPath('edit_file', null), null);
});

test('hasInlineDiff: 非空 inline_diff → true', () => {
  assert.strictEqual(hasInlineDiff({ inline_diff: '  @@ -1 +1 @@\n  ' }), true);
  assert.strictEqual(hasInlineDiff({ inline_diff: '' }), false);
  assert.strictEqual(hasInlineDiff({}), false);
});

test('SnapshotStore: set/get/has/delete/clear', () => {
  const s = new SnapshotStore();
  s.set({ absPath: '/a/b.ts', content: 'v1', existed: true, takenAt: 1, toolName: 'edit_file' });
  assert.strictEqual(s.has('/a/b.ts'), true);
  assert.strictEqual(s.get('/a/b.ts')?.content, 'v1');
  assert.strictEqual(s.size(), 1);
  s.delete('/a/b.ts');
  assert.strictEqual(s.has('/a/b.ts'), false);
  s.set({ absPath: '/a/b.ts', content: 'v1', existed: true, takenAt: 1, toolName: 'edit_file' });
  s.clear();
  assert.strictEqual(s.size(), 0);
});

test('Reject 逐字节还原：快照写回文件（md5 前后一致）', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'bobo-diff-'));
  const file = path.join(dir, 'sample.txt');
  const original = 'line1\nline2\nline3\n';
  fs.writeFileSync(file, original, 'utf8');
  const snapshot = { absPath: file, content: original, existed: true, takenAt: Date.now(), toolName: 'edit_file' };
  // 模拟 bobo 改动后
  fs.writeFileSync(file, 'line1\nCHANGED\nline3\n', 'utf8');
  assert.notStrictEqual(fs.readFileSync(file, 'utf8'), original, '改动后内容应不同');
  // Reject：快照写回
  restoreSnapshot(snapshot, fs, path);
  assert.strictEqual(fs.readFileSync(file, 'utf8'), original, '写回后应逐字节等于快照');
  assert.strictEqual(Buffer.byteLength(fs.readFileSync(file, 'utf8'), 'utf8'), Buffer.byteLength(original, 'utf8'));
  // 清理
  fs.rmSync(dir, { recursive: true, force: true });
});

test('Reject 写回不存在的目录：mkdirSync recursive 自动建', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'bobo-diff-'));
  const file = path.join(dir, 'nested', 'deep', 'new.txt');
  const snapshot = { absPath: file, content: 'hello', existed: true, takenAt: Date.now(), toolName: 'file_operation' };
  restoreSnapshot(snapshot, fs, path);
  assert.strictEqual(fs.readFileSync(file, 'utf8'), 'hello');
  fs.rmSync(dir, { recursive: true, force: true });
});

test('Reject 新建文件：existed=false 删除文件还原"不存在"', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'bobo-diff-'));
  const file = path.join(dir, 'created-by-bobo.txt');
  fs.writeFileSync(file, 'bobo wrote this', 'utf8');
  const snapshot = { absPath: file, content: 'bobo wrote this', existed: false, takenAt: Date.now(), toolName: 'file_operation' };
  restoreSnapshot(snapshot, fs, path);
  assert.strictEqual(fs.existsSync(file), false, 'existed=false 的 Reject 应删除文件');
  fs.rmSync(dir, { recursive: true, force: true });
});
