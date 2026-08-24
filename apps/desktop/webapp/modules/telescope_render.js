// ── 事件订阅（包装既有 handler：原逻辑先跑，Telescope 只追加观测，绝不覆盖）──
function _telWrap(type, mine) {
  var prev = handlers.get(type);
  handlers.set(type, function(data) {
    if (prev) prev(data);          // 原 handler 原样执行（异常照常冒泡，行为不变）
    try { mine(data); } catch (e) {}  // 观测逻辑异常不外泄，不干扰主链路
  });
}

function _telOnStart(data) {
  if (!_telEl) return;               // 面板未开过不消耗
  if (isForeignSession(data)) return;
  _telNewRound();
  _telRender();
}
function _telOnDelta(data) {
  if (!_telEl || !_telState) return;
  if (isForeignSession(data)) return;
  var t = data ? data.text || '' : '';
  if (!t) return;
  _telState.deltaBuf += t;
  if (!_telState.understand) _telState.understand = t.slice(0, 80);
  _telScheduleRender();   // delta 节流：rAF 合并，长回复不逐 token 全量重建
}
function _telOnToolStart(data) {
  if (!_telEl || !_telState) return;
  if (isForeignSession(data)) return;
  var name = data ? data.name || '' : '';
  var args = (data && data.arguments) ? data.arguments : {};
  var cat = _telCat(name);
  if (name === 'execute_terminal') {
    _telState.terminal.push({ command: String(args.command || data.context || ''), output: '', duration: 0, exitCode: null });
    _telScheduleRender();
    return;
  }
  if (name === 'task_ledger') { _telScheduleRender(); return; }  // 台账走独立 Task Ledger 区，不占 Tools 活表格
  _telState.calls[cat].push(_telRowStart(cat, name, args, data.context));  // 活表格：同 category 追加行，绝不新开表
  _telScheduleRender();
}
function _telOnToolComplete(data) {
  if (!_telEl || !_telState) return;
  if (isForeignSession(data)) return;
  var name = data ? data.name || '' : '';
  if (name === 'execute_terminal') { _telTermComplete(data); return; }
  if (name === 'task_ledger') { _telLedgerComplete(data); return; }
  var cat = _telCat(name);
  var rows = _telState.calls[cat];
  var row = rows.length ? rows[rows.length - 1] : null;
  if (!row) return;
  _telRowEnd(row, name, data);
  // 收尾小结数据：改动文件数/增删行/测试数字（真实事件累加）
  if (!data.error && _telIsWriteTool(name)) {
    _telState.files++;
    var st = _telDiffStats(data.inline_diff || '');
    _telState.addLines += st.add; _telState.delLines += st.del;
  }
  if (name === 'run_tests' && !data.error) {
    var m = String(data.result_text || '').match(/(\d+)\s+passed/);
    if (m) _telState.tests = m[0];
  }
  _telScheduleRender();
}
function _telOnComplete(data) {
  if (!_telEl || !_telState) return;
  if (isForeignSession(data)) return;
  _telState.summaryDone = true;
  var ft = (data && data.final_text) ? String(data.final_text) : '';
  // 一句人话结论：最终正文首句（思考段剥离与主聊天区同源 splitThinking）
  var body = splitThinking(ft).body;
  _telState.concl = body.split('\n').filter(function(l) { return l.trim(); })[0] || '';
  if (_telState.concl.length > 120) _telState.concl = _telState.concl.substring(0, 120) + '…';
  _telState.usage = (data && data.usage) ? data.usage : null;
  _telScheduleRender();
}

// 活表格行构造（start 半行 + complete 补结果）
function _telRowStart(cat, name, args, context) {
  var argStr = '';
  var keys = Object.keys(args || {});
  var parts = [];
  for (var i = 0; i < Math.min(2, keys.length); i++) {
    var k = keys[i];
    var v = args[k];
    if (v == null) v = '';
    v = String(v).replace(/\s+/g, ' ').trim();
    if (v.length > 28) v = v.substring(0, 28) + '…';
    parts.push(k + '=' + v);
  }
  argStr = parts.join(', ') || String(context || '');
  return { name: name, args: argStr, result: '…', dur: '—', diff: '', error: false };
}

function _telRowEnd(row, name, data) {
  row.dur = data.duration ? data.duration.toFixed(1) + 's' : '—';
  if (data.error) { row.error = true; row.result = 'Failed'; return; }
  var diff = data.inline_diff || '';
  var rt = String(data.result_text || '');
  if (_telIsWriteTool(name) && diff) {
    var st = _telDiffStats(diff);
    row.result = 'Wrote +' + st.add + ' / −' + st.del + ' lines';
    row.diff = diff;
  } else if (_telIsWriteTool(name)) {
    row.result = 'Write complete';
  } else {
    // 人话结果：raw JSON/日志不上屏，只取人读摘要
    row.result = _telHuman(rt);
  }
}

// 人话化结果文本：折叠空白 + 截断 80 字符
function _telHuman(rt) {
  var s = String(rt || '').trim().replace(/\s+/g, ' ').substring(0, 80);
  return s || '';
}

// task_ledger 工具结果 → 台账表格数据
function _telLedgerComplete(data) {
  var args = (data && data.arguments) ? data.arguments : {};
  var items = args.items;
  if (!items) return;
  var rows = [];
  (Array.isArray(items) ? items : [items]).forEach(function(it) {
    if (!it) return;
    var title = String(it.title || it.id || '');
    var status = String(it.status || 'pending');
    rows.push({ title: title, status: status });
  });
  _telState.ledger = { rows: rows };
  _telScheduleRender();
}

// execute_terminal 补全
function _telTermComplete(data) {
  var terms = _telState.terminal;
  var t = terms.length ? terms[terms.length - 1] : null;
  if (!t) return;
  t.output = String(data.result_text || '');
  t.duration = data.duration || 0;
  if (data.error) t.exitCode = 'Failed';
  _telScheduleRender();
}

// ── 面板入口与五区渲染 ──
function renderTelescopePanel(el) {
  _telEl = el;
  _telInitOnce();
  if (!_telState) _telState = _telBlankState();   // 首开空态：不递增轮次（轮次只由真实 message.start 驱动）
  _telRender();
}

function _telInitOnce() {
  if (_telInitDone) return;
  _telInitDone = true;
  _telWrap('message.start', _telOnStart);
  _telWrap('message.delta', _telOnDelta);
  _telWrap('tool.start', _telOnToolStart);
  _telWrap('tool.complete', _telOnToolComplete);
  _telWrap('message.complete', _telOnComplete);
  if (_telEl) _telEl.addEventListener('click', _telOnClick);
}

// ── delta 节流：rAF 合并渲染（理解卡只渲染一次；长回复不逐 token 全量重建）──
function _telScheduleRender() {
  _telDirty = true;
  if (_telRaf) return;
  var raf = (window && window.requestAnimationFrame)
    ? window.requestAnimationFrame.bind(window)
    : function(cb) { return setTimeout(cb, 16); };
  _telRaf = raf(function() {
    _telRaf = null;
    if (_telDirty) _telRender();   // _telRender 消费脏标记
  });
}

function _telRender() {
  _telDirty = false;   // 渲染即消费脏标记（同步渲染时挂起的 rAF 不再重复渲）
  if (!_telEl) return;
  var active = (_telTab === 'cost') ? 'cost' : 'battle';
  var html = '<div class="tel-tabs">'
    + '<button class="tel-tab' + (active === 'battle' ? ' active' : '') + '" data-tab="battle">Report</button>'
    + '<button class="tel-tab' + (active === 'cost' ? ' active' : '') + '" data-tab="cost">Cost</button>'
    + '</div>';
  // 战报 pane：轮次历史 + 当前轮
  html += '<div class="tel-pane" data-pane="battle"' + (active === 'battle' ? '' : ' style="display:none"') + '>';
  for (var i = 0; i < _telRounds.length; i++) html += _telRenderState(_telRounds[i], i);
  if (_telState) html += _telRenderState(_telState, '_cur');
  html += '</div>';
  // 消耗 pane：占位，内容由 _telRenderCost 异步填充（COST-1b）
  html += '<div class="tel-pane" data-pane="cost"' + (active === 'cost' ? '' : ' style="display:none"') + '></div>';
  _telEl.innerHTML = html;
  if (active === 'cost') _telRenderCost();
}

// 单轮渲染（含轮次分隔线）；srcKey 供折叠切换/diff 链接定位数据源（历史轮=数组索引，当前轮='_cur'）
function _telRenderState(st, srcKey) {
  if (!st) return '';
  var html = '';
  if (st.round > 0) html += '<div class="tel-round">── Round ' + st.round + ' ──</div>';
  html += _telRenderPrompt(st);
  html += _telRenderLedger(st);
  html += _telRenderCalls(st, srcKey);
  html += _telRenderTerminal(st, srcKey);
  html += _telRenderSummary(st);
  return html;
}

function _telRenderPrompt(st) {
  st = st || _telState;
  var html = '<div class="tel-sec"><div class="tel-sec-title">User prompt</div>';
  if (st.prompt) html += mdReply(st.prompt);
  else html += '<div class="tel-muted">(no user prompt snapshot this round)</div>';
  if (st.understand) {
    html += '<div class="tel-understand">' + mdReply('**Understood as**: ' + st.understand) + '</div>';
  }
  return html + '</div>';
}

function _telRenderLedger(st) {
  st = st || _telState;
  if (!st.ledger || !st.ledger.rows.length) return '';
  var md = '| # | Item | Status |\n|---|---|---|\n';
  st.ledger.rows.forEach(function(r, i) {
    md += '| ' + (i + 1) + ' | ' + String(r.title).replace(/\|/g, '\\|') + ' | ' + String(r.status) + ' |\n';
  });
  return '<div class="tel-sec"><div class="tel-sec-title">Task Ledger</div>' + mdReply(md) + '</div>';
}

function _telRenderCalls(st, srcKey) {
  st = st || _telState;
  srcKey = (srcKey == null) ? '_cur' : srcKey;
  var heads = { Skills: 'Skill | Loaded | Purpose', Memory: 'Item | Signal | Injection reason', Tools: 'Tool | Args | Result | Time' };
  var html = '';
  // TEL-b：单元格管道转义（与台账同款）——| 不打乱 Markdown 列结构；diff 链接是 HTML 非单元格文本，不受影响
  var escP = function(s) { return esc(s).replace(/\|/g, '\\|'); };
  ['Skills', 'Memory', 'Tools'].forEach(function(cat) {
    var rows = st.calls[cat];
    if (!rows.length) return;
    html += '<div class="tel-sec"><div class="tel-sec-title">' + cat + '</div>';
    var md = '| ' + heads[cat] + ' |\n|---|---|---|\n';
    rows.forEach(function(r, i) {
      var res = r.error ? '<span class="tel-muted">' + escP(r.result) + '</span>' : escP(r.result);
      var link = '';
      if (r.diff) link = ' <a href="#tel-diff-' + i + '" data-tel-src="' + srcKey + '">View diff</a>';
      if (cat === 'Tools') {
        md += '| `' + escP(r.name) + '` | ' + escP(r.args) + ' | ' + res + link + ' | ' + escP(r.dur) + ' |\n';
      } else {
        md += '| `' + escP(r.name) + '` | ' + escP(r.args) + ' | ' + res + ' |\n';
      }
    });
    html += mdReply(md) + '</div>';
  });
  return html;
}

function _telRenderTerminal(st, srcKey) {
  st = st || _telState;
  srcKey = (srcKey == null) ? '_cur' : srcKey;
  var terms = st.terminal;
  if (!terms.length) return '';
  var html = '<div class="tel-sec"><div class="tel-sec-title">Terminal run</div>';
  terms.forEach(function(t, i) {
    html += '<div class="tel-term" data-tel-src="' + srcKey + '">';
    html += '<div class="tel-term-cmd">' + mdReply('```\n$ ' + t.command + '\n```') + '</div>';
    var code = t.exitCode === 'Failed' ? 'Failed' : '—';
    html += '<div class="tel-term-meta">Time ' + (t.duration ? t.duration.toFixed(1) + 's' : '—') + ' · exit code ' + code + '</div>';
    if (t.output) {
      var long = t.output.length > 400;
      var shown = long ? t.output.substring(0, 200) + '\n… (output folded, ' + t.output.length + ' chars)' : t.output;
      html += '<div class="tel-term-out' + (long ? ' collapsed' : '') + '" data-i="' + i + '">' + esc(shown) + '</div>';
      if (long) html += '<button class="tel-term-toggle" data-i="' + i + '" onclick="telToggleTerm(this)">Expand all (' + t.output.length + ' chars)</button>';
    }
    html += '</div>';
  });
  return html + '</div>';
}

// 长输出折叠/展开切换（data-tel-src 定位所属轮：历史轮索引或 '_cur'）
function telToggleTerm(btn) {
  var term = btn.parentNode;
  while (term && (!term.getAttribute || !term.getAttribute('data-tel-src'))) term = term.parentNode;
  if (!term) return;
  var src = term.getAttribute('data-tel-src');
  var st = (src === '_cur') ? _telState : (_telRounds[parseInt(src, 10)] || _telState);
  var idx = parseInt(btn.getAttribute('data-i'), 10);
  var t = st.terminal[idx];
  if (!t) return;
  var out = term.querySelector('.tel-term-out');
  if (!out) return;
  var expanded = !out.classList.contains('collapsed');
  if (expanded) {
    out.classList.add('collapsed');
    out.textContent = t.output.substring(0, 200) + '\n… (output folded, ' + t.output.length + ' chars)';
    btn.textContent = 'Expand all (' + t.output.length + ' chars)';
  } else {
    out.classList.remove('collapsed');
    out.textContent = t.output;
    btn.textContent = 'Collapse';
  }
}

function _telRenderSummary(st) {
  st = st || _telState;
  if (!st.summaryDone) return '';
  var lines = ['**Round summary**'];
  if (st.files) lines.push('- Files changed: ' + st.files + ' · +' + st.addLines + ' / −' + st.delLines + ' lines');
  if (st.tests) lines.push('- Tests: ' + st.tests);
  if (st.usage) {
    var pct = (st.usage.context_percent != null) ? st.usage.context_percent + '%'
            : ((st.usage.total != null) ? st.usage.total : '—');
    lines.push('- token usage ' + pct);
  }
  if (st.concl) lines.push('> ' + st.concl);
  return '<div class="tel-sec"><div class="tel-sec-title">Wrap-up</div><div class="tel-summary">' + mdReply(lines.join('\n')) + '</div></div>';
}

// ── diff 模态弹层（✕ / Esc / 点背景关闭；diff 块与主聊天区同源 diffBlock 逐字节一致）──
function telShowDiff(diffText) {
  telCloseDiff();
  var ov = document.createElement('div'); ov.className = 'tel-modal-ov';
  var box = document.createElement('div'); box.className = 'tel-modal';
  var head = document.createElement('div'); head.className = 'tel-modal-head';
  head.innerHTML = '<span>Telescope · diff details</span><span class="tel-modal-x" onclick="telCloseDiff()">✕</span>';
  var body = document.createElement('div'); body.className = 'tel-modal-body';
  body.innerHTML = diffBlock(diffText);    // 同源 esc/diffBlock，与主聊天区 1:1
  box.appendChild(head); box.appendChild(body);
  ov.appendChild(box);
  ov.onclick = function(e) { if (e.target === ov) telCloseDiff(); };
  document.body.appendChild(ov);
  _telModalEl = ov;
}
function telCloseDiff() {
  if (_telModalEl && _telModalEl.parentNode) _telModalEl.parentNode.removeChild(_telModalEl);
  _telModalEl = null;
}
// Esc 关闭：capture 阶段优先拦截（modal 开着时只关 modal，不触发主窗 stopThinking —— 零干涉）
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape' && _telModalEl) { e.stopPropagation(); telCloseDiff(); }
}, true);

// 面板内事件委托：#tel-diff-N 链接 → 弹模态层（data-tel-src 定位所属轮）
// ── COST-1b：消耗页签（读 rounds.jsonl 最近 N 条，全 Markdown/图表化，零 raw）──
function _telHtmlEsc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function _telRenderCost() {
  var pane = _telEl && _telEl.querySelector('[data-pane="cost"]');
  if (!pane) return;
  pane.innerHTML = '<div class="tel-muted">Loading metrics…</div>';
  call('metrics.read', { limit: 50 }).then(function(res) {
    if (!pane) return;
    var rounds = (res && res.rounds) || [];
    if (!rounds.length) {
      pane.innerHTML = '<div class="tel-muted">No cost data yet (rounds.jsonl empty, or no rounds completed in this run)</div>';
      return;
    }
    pane.innerHTML = _telCostHtml(rounds);
  });
}
function _telCostHtml(rounds) {
  var cur = rounds[0];   // metrics.read 返回新→旧，[0]=最近一轮
  var h = '<div class="tel-sec"><div class="tel-sec-title">Round breakdown · ' + cur.round + '</div>'
    + _telCostBar(cur) + '</div>';
  h += '<div class="tel-sec"><div class="tel-sec-title">Cache hit rate</div>' + _telCacheRate(rounds) + '</div>';
  var warn = _telRepeatWarn(cur);
  if (warn) h += '<div class="tel-sec"><div class="tel-sec-title">Redundant work warning</div>' + warn + '</div>';
  h += '<div class="tel-cost-note">Source: data/metrics/rounds.jsonl (one row per message.complete) · read-only</div>';
  return h;
}
function _telCostBar(r) {
  var u = r.usage || {};
  var prompt = u.prompt_tokens || 0;
  var userChars = u.user_prompt_chars || 0;      // 用户输入（字符；弱灰，不计入优化口径）
  var b = r.budget || {};
  var inject = 0;
  [b.system, b.discipline, b.memory, b.pointers].forEach(function(v) {
    if (typeof v === 'number') inject += v;
  });
  var base = Math.max(prompt, 1);
  var userPct = Math.min(100, Math.round(userChars / base * 100));
  var injectPct = Math.min(100, Math.round(inject / base * 100));
  var schedPct = Math.max(0, 100 - userPct - injectPct);
  return '<div class="tel-bar-wrap">'
    + '<div class="tel-bar">'
    + '<div class="tel-bar-seg tel-bar-user" style="width:' + userPct + '%" title="User input ' + userChars + ' chars"></div>'
    + '<div class="tel-bar-seg tel-bar-inject" style="width:' + injectPct + '%" title="Injection ' + inject + ' chars"></div>'
    + '<div class="tel-bar-seg tel-bar-sched" style="width:' + schedPct + '%" title="History & tool results (scheduling)"></div>'
    + '</div>'
    + '<div class="tel-bar-legend">'
    + '<span><i style="background:#b8b4a8"></i>User input ' + userChars + ' (not counted)</span>'
    + '<span><i style="background:#777"></i>Injection ' + inject + '</span>'
    + '<span><i style="background:#e8913a"></i>History & tool results (scheduling)</span>'
    + '</div>'
    + '<div class="tel-muted">Total prompt tokens ' + prompt + ' · injection=system+discipline+memory+pointers chars (approx; chars≠tokens)</div>'
    + '</div>';
}
function _telCacheRate(rounds) {
  var cur = rounds[0].usage || {};
  var hit = 0, miss = 0, n = 0;
  rounds.slice(0, 10).forEach(function(r) {
    var u = r.usage || {};
    var h = u.cache_hit_tokens, m = u.cache_miss_tokens;
    if (typeof h === 'number' && typeof m === 'number') { hit += h; miss += m; n++; }
  });
  var curHit = cur.cache_hit_tokens, curMiss = cur.cache_miss_tokens;
  if (typeof curHit !== 'number' || typeof curMiss !== 'number') {
    return '<div class="tel-warn"><p>Cache fields not forwarded from DeepSeek usage (gateway relay lacks prompt_cache_hit_tokens / prompt_cache_miss_tokens); hit rate unavailable — slots reserved.</p></div>';
  }
  var pct = (hit + miss) > 0 ? Math.round(hit / (hit + miss) * 100) : 0;
  var curPct = (curHit + curMiss) > 0 ? Math.round(curHit / (curHit + curMiss) * 100) : 0;
  return '<div class="tel-muted">This round: ' + curPct + '% (' + curHit + '/' + (curHit + curMiss) + ') · last ' + (n || 1) + '-round avg ' + pct + '%</div>';
}
function _telRepeatWarn(r) {
  var rr = r.repeat_reads || [];
  if (!rr.length) return '';
  var items = rr.map(function(x) {
    return '<p>⚠ Repeated read <code>' + _telHtmlEsc(x.target) + '</code> × ' + x.count + '</p>';
  }).join('');
  return '<div class="tel-warn">' + items + '</div>';
}

function _telOnClick(e) {
  var t = e && e.target;
  // COST-1b：页签切换（战报 | 消耗）
  if (t && t.tagName === 'BUTTON' && t.getAttribute && t.getAttribute('data-tab')) {
    var tab = t.getAttribute('data-tab');
    if (tab === _telTab) return;
    _telTab = tab;
    _telRender();
    return;
  }
  var a = t;
  while (a && a.tagName !== 'A') a = a.parentNode;
  if (!a) return;
  var href = (a.getAttribute && a.getAttribute('href')) || '';
  if (href.indexOf('#tel-diff-') !== 0) return;
  e.preventDefault();
  var i = parseInt(href.substring('#tel-diff-'.length), 10);
  var src = a.getAttribute('data-tel-src') || '_cur';
  var st = (src === '_cur') ? _telState : (_telRounds[parseInt(src, 10)] || _telState);
  var row = st.calls.Tools[i];
  if (row && row.diff) telShowDiff(row.diff);
}
// ── end TICKET-DESK-TEL ──