// parts.js — TICKET-VSC-2：面板 UI 组件 HTML 构建（纯函数，无 DOM，node:test 可测）。
// 票 VSC-2B：工具聚合卡移植桌面端（addTool/toolSummary/appendDiffBlock 结构对齐）；
// tool-row 一排散落废弃；diff 卡（Accept/Reject）废弃 → 审批卡（approval.request）。
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

// ── VSC-2B：工具图标（对齐桌面端 toolIcon 语义：映射 + _default 回退，不许空白）──
// VSC-2C：emoji → 桌面端同款细线 SVG（apps/desktop/dist/index.html:1419+ 逐条复制，
// class="tool-ic" 保留；桌面端无对应键的同族复用，未知回退 _default）——GUI-LESSONS L4
var TOOL_ICONS = {
  'edit_file': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.1 11.4 L3.65 8.9 8.9 3.65 c.35-.35 .92-.35 1.27 0 l.18.18 c.35.35 .35.92 0 1.27 L5.1 10.35 l-2.5.65 z"/><path d="M2.3 12.2 h9.4"/></svg>',
  'file_operation': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.1 11.4 L3.65 8.9 8.9 3.65 c.35-.35 .92-.35 1.27 0 l.18.18 c.35.35 .35.92 0 1.27 L5.1 10.35 l-2.5.65 z"/><path d="M2.3 12.2 h9.4"/></svg>',
  'file_writer': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.1 11.4 L3.65 8.9 8.9 3.65 c.35-.35 .92-.35 1.27 0 l.18.18 c.35.35 .35.92 0 1.27 L5.1 10.35 l-2.5.65 z"/><path d="M2.3 12.2 h9.4"/></svg>',
  'refactor': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.1 11.4 L3.65 8.9 8.9 3.65 c.35-.35 .92-.35 1.27 0 l.18.18 c.35.35 .35.92 0 1.27 L5.1 10.35 l-2.5.65 z"/><path d="M2.3 12.2 h9.4"/></svg>',
  'grep_code': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="6" cy="6" r="3.4"/><path d="M8.6 8.6 L11.5 11.5"/></svg>',
  'search_obsidian': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="6" cy="6" r="3.4"/><path d="M8.6 8.6 L11.5 11.5"/></svg>',
  'cross_search': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="6" cy="6" r="3.4"/><path d="M8.6 8.6 L11.5 11.5"/></svg>',
  'read_local_file': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 1.75 h3.5 l3.25 3.25 V12.25 H4 Z"/><path d="M7.25 1.75 v3.5 h3.5"/></svg>',
  'read_obsidian': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 1.75 h3.5 l3.25 3.25 V12.25 H4 Z"/><path d="M7.25 1.75 v3.5 h3.5"/></svg>',
  'list_directory': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 1.75 h3.5 l3.25 3.25 V12.25 H4 Z"/><path d="M7.25 1.75 v3.5 h3.5"/></svg>',
  'execute_terminal': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="1.75" y="2.75" width="10.5" height="8.5" rx="1.5"/><path d="M4.25 5.25 L6 7 L4.25 8.75"/><path d="M7.5 8.75 h2.25"/></svg>',
  'code_execution': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="1.75" y="2.75" width="10.5" height="8.5" rx="1.5"/><path d="M4.25 5.25 L6 7 L4.25 8.75"/><path d="M7.5 8.75 h2.25"/></svg>',
  'run_tests': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.75 7.5 L5.5 10.25 L11.25 3.75"/></svg>',
  'web_search': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="7" cy="7" r="4.25"/><path d="M2.75 7 h8.5 M7 2.75 c-1.2 1.35 -1.2 6.15 0 8.5 M7 2.75 c1.2 1.35 1.2 6.15 0 8.5"/></svg>',
  'web_fetch': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="7" cy="7" r="4.25"/><path d="M2.75 7 h8.5 M7 2.75 c-1.2 1.35 -1.2 6.15 0 8.5 M7 2.75 c1.2 1.35 1.2 6.15 0 8.5"/></svg>',
  'write_obsidian': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.1 11.4 L3.65 8.9 8.9 3.65 c.35-.35 .92-.35 1.27 0 l.18.18 c.35.35 .35.92 0 1.27 L5.1 10.35 l-2.5.65 z"/><path d="M2.3 12.2 h9.4"/></svg>',
  'append_obsidian': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.1 11.4 L3.65 8.9 8.9 3.65 c.35-.35 .92-.35 1.27 0 l.18.18 c.35.35 .35.92 0 1.27 L5.1 10.35 l-2.5.65 z"/><path d="M2.3 12.2 h9.4"/></svg>',
  'task_ledger': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 4.25 h8 M3 7 h8 M3 9.75 h8"/></svg>',
  'save_memory': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2.5" y="2.5" width="9" height="9" rx="1.75"/><path d="M7 4.9 L9.1 7 L7 9.1 L4.9 7 Z"/></svg>',
  'search_memory': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2.5" y="2.5" width="9" height="9" rx="1.75"/><path d="M7 4.9 L9.1 7 L7 9.1 L4.9 7 Z"/></svg>',
  'load_result': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2.5" y="2.5" width="9" height="9" rx="1.75"/><path d="M7 4.9 L9.1 7 L7 9.1 L4.9 7 Z"/></svg>',
  '_default': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="8" height="8" rx="1.25"/></svg>'
};
function toolIcon(name) { return TOOL_ICONS[name] || TOOL_ICONS['_default']; }

// ── VSC-2B：工具一行摘要（对齐桌面端 toolSummary：路径 +N/-M；无 diff 时路径即可）──
function diffStats(inlineDiff) {
  var add = 0; var del = 0;
  String(inlineDiff || '').split('\n').forEach(function (l) {
    if (/^\+/.test(l) && !/^\+\+\+/.test(l)) add++;
    else if (/^-/.test(l) && !/^---/.test(l)) del++;
  });
  return { add: add, del: del };
}
function toolSummary(args, inlineDiff) {
  var pathKeys = ['file_path', 'path', 'filepath', 'filename', 'source', 'target'];
  var p = '';
  for (var i = 0; i < pathKeys.length; i++) {
    var v = args[pathKeys[i]];
    if (typeof v === 'string' && v) { p = v; break; }
  }
  var st = diffStats(inlineDiff);
  return (p ? p : '') + (st.add + st.del ? ' +' + st.add + '/-' + st.del : '');
}

// ── VSC-2B：diff 只读块（对齐桌面端 diffBlock：@@ 文件头 / +绿 / -红 / 上下文灰）──
function buildDiffBlock(inlineDiff) {
  var lines = escapeHtml(inlineDiff || '').split('\n');
  var html = '<div class="diff-block">';
  lines.forEach(function (l) {
    if (/^@@/.test(l)) html += '<div class="df">' + l + '</div>';
    else if (/^\+/.test(l) && !/^\+\+\+/.test(l)) html += '<div class="dl add">' + l + '</div>';
    else if (/^-/.test(l) && !/^---/.test(l)) html += '<div class="dl del">' + l + '</div>';
    else html += '<div class="dl ctx">' + (l ? l : '&nbsp;') + '</div>';
  });
  html += '</div>';
  return html;
}

// ── VSC-2B：工具聚合卡容器（"N 个工具调用"一行，点击展开 body）──
function buildToolAggCard() {
  return '<div class="tool-agg"><span class="tool-agg-head"><span class="tool-agg-arrow">▸</span><span class="tool-agg-title">0 个工具调用</span></span><div class="tool-agg-body" style="display:none"></div></div>';
}

// ── VSC-2B：工具卡（对齐桌面端 addTool 结构：icon + dot + name + context + toggle + result）──
function buildToolItem(ev) {
  var name = String(ev.name || 'tool');
  var isStart = (ev.type || 'tool.start') === 'tool.start';
  var args = (ev && typeof ev.arguments === 'object' && ev.arguments) || {};
  var friendly = name;
  var dotCls = isStart ? 'run' : (ev.error ? 'fail' : 'done');
  var summary = isStart
    ? (args.file_path || args.path || args.query || args.action || '')
    : toolSummary(args, ev.inline_diff);
  var html = '<div class="tool" data-name="' + escapeHtml(name) + '" data-state="' + dotCls + '">'
    + '<span class="tool-icon">' + toolIcon(name) + '</span>'
    + '<span class="tool-dot ' + dotCls + '"></span>'
    + '<span class="tool-name">' + escapeHtml(friendly) + '</span>'
    + (summary ? '<span class="tool-context">' + escapeHtml(summary).slice(0, 240) + '</span>' : '')
    + '<span class="tool-toggle" style="display:none">▸</span>'
    + '<div class="tool-result"></div>'
    + '</div>';
  if (!isStart) {
    var bodyText = '';
    if (ev.error) bodyText = String(ev.error);
    else if (typeof ev.result_text === 'string' && ev.result_text) bodyText = ev.result_text.slice(0, 2000);
    if (bodyText) {
      html += '<div class="tool-body"><pre>' + escapeHtml(bodyText) + '</pre></div>';
    }
  }
  return html;
}

// ── VSC-2B：审批卡（执行前无 diff；tool_name + arguments 摘要 + Accept/Reject）──
function buildApprovalCard(ev) {
  var name = String(ev.tool_name || ev.name || 'tool');
  var args = (ev && typeof ev.arguments === 'object' && ev.arguments) || {};
  var lines = [];
  Object.keys(args).forEach(function (k) {
    var v = args[k];
    var s = typeof v === 'string' ? v : JSON.stringify(v);
    if (!s || s.length > 160) s = (s || '').slice(0, 160) + '…';
    lines.push(escapeHtml(k) + ': ' + escapeHtml(s));
  });
  return '<div class="approval-card" data-name="' + escapeHtml(name) + '">'
    + '<div class="approval-title"><span class="tool-icon">' + toolIcon(name) + '</span><span>' + escapeHtml(name) + ' 请求写审批</span></div>'
    + '<div class="approval-args">' + (lines.length ? lines.join('<br>') : '(无参数)') + '</div>'
    + '<div class="diff-actions">'
    + '<button class="approve">Accept</button>'
    + '<button class="reject">Reject</button>'
    + '</div></div>';
}

// ── VSC-2B：思考折叠块（默认收起；点击展开由 chat.js 绑交互）──
function buildThinkBlock(text) {
  var safe = escapeHtml(text);
  return '<div class="think-box">'
    + '<div class="think-label"><span class="think-caret">›</span><span>思考过程</span></div>'
    + '<div class="think-text">' + safe + '</div>'
    + '</div>';
}

// ── VSC-2D：台账条目（标题 + 状态点）──
function buildLedgerItem(it) {
  var st = it.status || 'pending';
  return '<div class="lg-item"><span class="lg-dot ' + escapeHtml(st) + '"></span>'
    + '<span class="lg-title">' + escapeHtml(it.title || it.id || '') + '</span></div>';
}

// ── VSC-2B：会话下拉条目 ──
function buildSessionItem(s, active) {
  return '<div class="sess-item' + (active ? ' active' : '') + '" data-id="' + escapeHtml(s.id) + '">'
    + '<div>' + escapeHtml(s.title || s.id) + '</div>'
    + '<div class="sess-meta">' + (s.message_count || 0) + ' msgs</div></div>';
}

// ── 票 VSC-2B：审批卡 Accept/Reject → approval.respond choice 映射（可测）──
var APPROVAL_CHOICES = { accept: 'allow', reject: 'deny' };

// ── 票 VSC-2B：审批卡串行闸门状态机（纯逻辑，node:test 可测）──
// 语义：同一时刻只允许一张审批卡。open 新卡时自动关闭上一张（触发 onClose），
// 引擎天然串行（pending_confirm 按 sid 单槽），此为扩展侧再保险（防双弹）。
function createApprovalGate() {
  var current = null;
  var seq = 0;
  return {
    /** 挂新卡：关闭旧卡（onClose 回调），返回新卡 id。 */
    open: function (onClose) {
      seq++;
      var id = seq;
      if (current) {
        var old = current;
        current = null;
        if (old.onClose) old.onClose(old.id);
      }
      current = { id: id, onClose: onClose || null, timedOut: false };
      return id;
    },
    /** 关当前卡（触发 onClose）。 */
    close: function () {
      if (!current) return null;
      var old = current;
      current = null;
      if (old.onClose) old.onClose(old.id);
      return old.id;
    },
    /** 当前卡超时置灰（返回卡 id；无卡返回 null）。 */
    timeout: function () {
      if (!current) return null;
      current.timedOut = true;
      return current.id;
    },
    /** 当前卡（只读）。 */
    get current() { return current; },
    get hasOpen() { return !!current; },
  };
}

// ── 票 VSC-2B：停止按钮 Send⇄Stop 可见性映射（可测）──
// running=true → 隐藏 Send、显示 Stop；false 反之。
function runningView(running) {
  return { send: running ? 'none' : '', stop: running ? 'show' : '' };
}

// 双环境（与 md-render.js 同模式）：浏览器挂 window.parts；Node require 导出。
if (typeof module === 'object' && module.exports) {
  module.exports = { escapeHtml, buildThinkBlock, buildToolAggCard, buildToolItem, buildApprovalCard, buildDiffBlock, toolSummary, buildLedgerItem, buildSessionItem, APPROVAL_CHOICES, createApprovalGate, runningView, TOOL_ICONS, toolIcon };
} else {
  window.parts = { escapeHtml, buildThinkBlock, buildToolAggCard, buildToolItem, buildApprovalCard, buildDiffBlock, toolSummary, buildLedgerItem, buildSessionItem, APPROVAL_CHOICES, createApprovalGate, runningView, TOOL_ICONS, toolIcon };
}
