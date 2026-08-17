// parts.js — TICKET-VSC-2：面板 UI 组件 HTML 构建（纯函数，无 DOM，node:test 可测）。
// 与 md-render.js 同模式：media 下独立纯 JS，chat.js 消费。
// 安全模型：所有外来字符串先 escapeHtml，禁止 raw 直插。
'use strict';

function escapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── VSC-2B：思考折叠块（默认收起；点击展开由 chat.js 绑交互）──
function buildThinkBlock(text) {
  const safe = escapeHtml(text);
  return '<div class="think-box">'
    + '<div class="think-label"><span class="think-caret">›</span><span>思考过程</span></div>'
    + '<div class="think-text">' + safe + '</div>'
    + '</div>';
}

// ── VSC-2B：工具行（start=run 点 / complete=done|fail 点 + 摘要 + 可展开体）──
function buildToolRow(ev) {
  const name = escapeHtml(ev.name || 'tool');
  const isStart = (ev.type || 'tool.start') === 'tool.start';
  const args = ev.arguments || {};
  let brief = '';
  if (isStart) {
    brief = args.file_path || args.path || args.query || args.action || '';
  } else {
    brief = ev.error ? String(ev.error) : '';
  }
  const dotCls = isStart ? 'run' : (ev.error ? 'fail' : 'done');
  const ctx = escapeHtml(brief).slice(0, 240);
  let html = '<div class="tool-row" data-name="' + name + '" data-done="' + (isStart ? '0' : '1') + '">'
    + '<span class="tool-dot ' + dotCls + '"></span>'
    + '<span class="tool-name">' + name + '</span>'
    + '<span class="tool-ctx">' + ctx + '</span>'
    + '<span class="tool-caret">›</span>'
    + '</div>';
  if (!isStart) {
    const bodyText = (ev.inline_diff || (typeof ev.result_text === 'string' ? ev.result_text : '')).slice(0, 2000);
    if (bodyText) {
      html += '<div class="tool-body"><pre>' + escapeHtml(bodyText) + '</pre></div>';
    }
  }
  return html;
}

// ── VSC-2C：diff 卡（Accept/Reject 按钮）──
function buildDiffCard(filePath, title) {
  return '<div class="diff-card" data-file="' + escapeHtml(filePath) + '">'
    + '<div class="diff-file">' + escapeHtml(title || filePath) + '</div>'
    + '<div class="diff-actions">'
    + '<button class="accept">Accept</button>'
    + '<button class="reject">Reject</button>'
    + '</div></div>';
}

// ── VSC-2D：台账条目（标题 + 状态点）──
function buildLedgerItem(it) {
  const st = it.status || 'pending';
  return '<div class="lg-item"><span class="lg-dot ' + escapeHtml(st) + '"></span>'
    + '<span class="lg-title">' + escapeHtml(it.title || it.id || '') + '</span></div>';
}

// ── VSC-2B：会话下拉条目 ──
function buildSessionItem(s, active) {
  return '<div class="sess-item' + (active ? ' active' : '') + '" data-id="' + escapeHtml(s.id) + '">'
    + '<div>' + escapeHtml(s.title || s.id) + '</div>'
    + '<div class="sess-meta">' + (s.message_count || 0) + ' msgs</div></div>';
}

// 双环境（与 md-render.js 同模式）：浏览器挂 window.parts；Node require 导出。
if (typeof module === 'object' && module.exports) {
  module.exports = { escapeHtml, buildThinkBlock, buildToolRow, buildDiffCard, buildLedgerItem, buildSessionItem };
} else {
  window.parts = { escapeHtml, buildThinkBlock, buildToolRow, buildDiffCard, buildLedgerItem, buildSessionItem };
}
