// contrast.test.js — TICKET-VSC-2A 对比度矩阵断言（WCAG AA ≥ 4.5:1）
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { contrastRatio, assertContrast, PALETTE } = require('../out/contrast.js');

test('相对亮度与对比度基本公式（WCAG 已知样本）', () => {
  // 纯黑 vs 纯白 = 21:1
  assert.ok(Math.abs(contrastRatio('#000000', '#ffffff') - 21) < 0.01, '黑白对比度应约 21:1');
  // 相同颜色 = 1:1
  assert.strictEqual(contrastRatio('#2d2d2d', '#2d2d2d'), 1);
});

test('对比度矩阵：主内容文字 --text 在全部背景 ≥4.5:1', () => {
  for (const [bname, bg] of Object.entries({ bg: PALETTE.bg, bg2: PALETTE.bg2, bg3: PALETTE.bg3 })) {
    assertContrast(PALETTE.text, bg, 4.5);
    assert.ok(contrastRatio(PALETTE.text, bg) >= 11, `--text vs ${bname} 应 ≥11:1`);
  }
});

test('对比度矩阵：次级内容 --text2 在全部背景 ≥4.5:1', () => {
  for (const [bname, bg] of Object.entries({ bg: PALETTE.bg, bg2: PALETTE.bg2, bg3: PALETTE.bg3 })) {
    const r = assertContrast(PALETTE.text2, bg, 4.5);
    assert.ok(r >= 5, `--text2 vs ${bname} 应 ≥5:1（实际 ${r.toFixed(2)}）`);
  }
});

test('对比度矩阵：占位符 --text-muted 在输入框背景 ≥4.5:1', () => {
  // 输入框背景是 --bg；--text-muted 只允许用于占位符/装饰（退出内容文字）
  assertContrast(PALETTE.textMuted, PALETTE.bg, 4.5);
});

test('对比度矩阵：hljs 语义色在代码块背景 --bg3 ≥4.5:1', () => {
  const fgOnCode = [
    ['关键词橙', PALETTE.accentOrange],
    ['字符串绿', PALETTE.stringGreen],
    ['数字黄褐', PALETTE.numberBrown],
    ['diff 删色', PALETTE.diffDel],
  ];
  for (const [name, fg] of fgOnCode) {
    assertContrast(fg, PALETTE.bg3, 4.5);
  }
  // 注释用 --text2（代码块内），一并断言
  assertContrast(PALETTE.text2, PALETTE.bg3, 4.5);
});

test('对比度矩阵：diff 增/删色在正文背景 --bg ≥4.5:1', () => {
  assertContrast(PALETTE.stringGreen, PALETTE.bg, 4.5); // diff-add
  assertContrast(PALETTE.diffDel, PALETTE.bg, 4.5);     // diff-del
});

test('旧值回归防护：票基准上的不达标旧值被拒（防回退）', () => {
  // 这些旧值在代码块背景上不达标，任何"回退到旧色"的改动都会被此测试拦住
  const oldValues = ['#e8913a', '#50a14f', '#999', '#8a6d3b', '#7ec87b', '#f48771', '#777'];
  for (const old of oldValues) {
    assert.throws(() => assertContrast(old, PALETTE.bg3, 4.5), `旧值 ${old} 不得达标`);
  }
});

// ── 票 VSC-2C：代码块/目录树场景回归闸（owner 实弹：目录树/代码条对比度太低）──
test('VSC-2C 代码块场景：无语言 pre code 文字色（--text）vs --bg3 ≥4.5:1', () => {
  // chatPanel.ts `.msg.bobo .txt pre code` 无显式 color，继承 body --text；
  // 任何给 pre code 显式赋低对比色、或把代码块前景改成 muted 的改动都会被此测试拦住。
  assertContrast(PALETTE.text, PALETTE.bg3, 4.5);
});

test('VSC-2C 目录树/次级列表场景：--text2 在代码块背景 --bg3 ≥4.5:1', () => {
  // 回复目录树/代码条若以 --text2 作前景，必须满足 WCAG AA（实测 ≥5:1）
  assertContrast(PALETTE.text2, PALETTE.bg3, 4.5);
});

test('VSC-2C 内容文字禁 --text-muted：muted 在代码块背景必须 <4.5:1（证明不可作代码块内容前景）', () => {
  // --text-muted 只允许占位符/装饰，退出内容文字（派单：内容文字禁 --text-muted）。
  // 若某次改动把 muted 提到 ≥4.5（比如加深），就会破坏"muted 不是内容色"的语义，
  // 代码块/目录树内容可能被误用 muted——此闸阻止该方向。
  const r = contrastRatio(PALETTE.textMuted, PALETTE.bg3);
  assert.ok(r < 4.5, `muted vs --bg3 必须 <4.5:1（实际 ${r.toFixed(2)}），否则会被误用于代码块内容`);
});
