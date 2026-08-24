// ── Sidebar Sections & Plugin System ──
function toggleSection(name) {
  var body = document.getElementById('body-' + name);
  var arrow = document.getElementById('arr-' + name);
  body.classList.toggle('closed');
  arrow.classList.toggle('closed');
}

// ── 票 P0-1 改版：导航项（New session / Memory / Session）+ Memory 主面板视图 ──
function setNavActive(id) {
  ['nav-new-session', 'nav-memory', 'nav-session', 'nav-skills'].forEach(function(n) {
    var el = document.getElementById(n);
    if (el) el.classList.toggle('active', el.id === id);
  });
}

// 视图互斥（owner 实弹：点开 A 必须覆盖 B——memory/skills/chat 只显示一个）
// 当前激活视图追踪：'nav-memory' | 'nav-skills' | ''（聊天）。异步回调
// （loadSession await 返回）据此判断"是否该抢回聊天视图"——用户已切走
// 则不抢（修复竞态：点 session 后立刻点 memory，loadSession 返回不再覆盖）。
var _activeView = '';

function setView(v) {
  _activeView = v;
  setNavActive(v);
}

function hideAllViews() {
  var mv = document.getElementById('memory-view');
  if (mv) mv.style.display = 'none';
  var sv = document.getElementById('skills-view');
  if (sv) sv.style.display = 'none';
  // 视图模式下输入框必须一起隐藏（#main 是 flex 列，input-box 在视图下方
  // 会露出来——owner 实弹：点 memory/skills 后"下面还有对话框"）
  var ib = document.getElementById('input-box');
  if (ib) ib.style.display = 'none';
  var cs = document.getElementById('ctx-stats-wrap');
  if (cs) cs.style.display = 'none';
}

function showInputBox() {
  var ib = document.getElementById('input-box');
  if (ib) ib.style.display = '';
  var cs = document.getElementById('ctx-stats-wrap');
  if (cs) cs.style.display = '';
}

function showMainChat() {
  hideAllViews();
  showInputBox();  // 恢复输入框（hideAllViews 已隐藏）
  var w = document.getElementById('welcome');
  var c = document.getElementById('chat');
  if (w) w.style.display = '';
  if (c) c.style.display = '';
  setView('');
}

function onNavNewSession() {
  hideAllViews();  // 覆盖 memory/skills 等视图（互斥），回到聊天区
  if (typeof newChat === 'function') newChat();
}

function onNavMemory() {
  var mv = document.getElementById('memory-view');
  if (!mv) return;
  hideAllViews();  // 覆盖 skills 等其它视图（互斥）
  var w = document.getElementById('welcome');
  var c = document.getElementById('chat');
  if (w) w.style.display = 'none';
  if (c) c.style.display = 'none';
  mv.style.display = 'block';
  setView('nav-memory');
  loadMemoryPanel();
}

function closeMemoryView() {
  showMainChat();
}

// ── 票 TICKET-SKILL-PANEL v2（owner 实弹反馈）：Skills 主面板视图 ──
// 与 Memory 同款：左侧栏导航项（SVG+名称+hover 高亮）→ 点击主区列出全部
// skills（preset/custom 分组 + on/off 开关）。skills.list/toggle RPC 后端已有。
function onNavSkills() {
  var sv = document.getElementById('skills-view');
  if (!sv) return;
  hideAllViews();  // 覆盖 memory 等其它视图（互斥）
  var w = document.getElementById('welcome');
  var c = document.getElementById('chat');
  if (w) w.style.display = 'none';
  if (c) c.style.display = 'none';
  sv.style.display = 'block';
  setView('nav-skills');
  loadSkillsPanel();
}

function closeSkillsView() {
  showMainChat();
}

function loadSkillsPanel() {
  call('skills.list', {}).then(function(r) {
    var g = document.getElementById('skills-groups');
    if (!g) return;
    if (!r || (!r.preset && !r.custom)) {
      g.innerHTML = '<div class="mem-empty">Load failed — skills.list unavailable.</div>';
      return;
    }
    var preset = r.preset || [], custom = r.custom || [];
    var total = preset.length + custom.length;
    var st = document.getElementById('skills-stats');
    if (st) st.textContent = total + ' skills';
    var cnt = document.getElementById('skills-count');
    if (cnt) cnt.textContent = total;
    var html = '';
    // Preset 组
    html += '<div class="skills-sec-label">Preset</div>';
    if (preset.length === 0) {
      html += '<div class="mem-empty">No preset skills.</div>';
    } else {
      html += '<div class="skills-list">';
      preset.forEach(function(it) {
        html += renderSkillRow(it);
      });
      html += '</div>';
    }
    // Custom 组（B 票自动沉淀后出现）
    html += '<div class="skills-sec-label">Custom</div>';
    if (custom.length === 0) {
      html += '<div class="mem-empty">Auto-generated skills will appear here when bobo learns a repeatable workflow.</div>';
    } else {
      html += '<div class="skills-list">';
      custom.forEach(function(it) {
        html += renderSkillRow(it);
      });
      html += '</div>';
    }
    g.innerHTML = html;
  });
}

function renderSkillRow(it) {
  var name = String(it.name || '');
  var on = !!it.enabled;
  return '<div class="skills-row">' +
    '<span class="skills-name">' + esc(name) + '</span>' +
    '<button class="skill-toggle' + (on ? ' on' : '') + '" ' +
    'onclick="toggleSkill(this, \'' + name.replace(/'/g, "\\'") + '\')">' +
    (on ? 'on' : 'off') + '</button></div>';
}

function toggleSkill(btn, name) {
  var cur = btn.classList.contains('on');
  call('skills.toggle', { skill_name: name, enabled: !cur }).then(function() {
    loadSkillsPanel();  // 刷新（后端下一轮注入即生效）
  });
}

// ── 票 P0-1：Memory 面板（六类分组 + diff 增删 + 手动编辑）────────────────
var MEMORY_TYPES = ['USER_PREF', 'RULES', 'FACT', 'ACHIEVEMENT', 'LESSON', 'GOAL'];
var MEMORY_TYPE_LABEL = { USER_PREF:'User Pref', RULES:'Rules', FACT:'Fact', ACHIEVEMENT:'Achievement', LESSON:'Lesson', GOAL:'Goal' };
var memorySnapshot = {};  // id -> text，用于 diff 增删对比

function memTypeLabel(t) { return MEMORY_TYPE_LABEL[t] || t; }

function renderMemoryDiff(newIds) {
  var el = document.getElementById('memory-diff');
  var lines = [];
  Object.keys(memorySnapshot).forEach(function(id) {
    if (!(id in newIds)) lines.push('- [' + id + '] ' + memorySnapshot[id]);
  });
  Object.keys(newIds).forEach(function(id) {
    if (!(id in memorySnapshot)) lines.push('+ [' + id + '] ' + newIds[id]);
  });
  if (!lines.length) { el.style.display = 'none'; return; }
  el.innerHTML = '<div class="mem-diff-title">CHANGES</div>' + diffBlock(lines.join('\n'));
  el.style.display = 'block';
  // 快照更新放到渲染成功后（由 loadMemoryPanel 末尾统一做）
}

function renderMemoryGroups(data) {
  var groupsEl = document.getElementById('memory-groups');
  var html = '';
  var totalEntries = 0;
  MEMORY_TYPES.forEach(function(t) {
    var g = data.groups[t];
    totalEntries += g.count;
    var entries = g.entries.slice(0, 40);
    var rows = '';
    entries.forEach(function(en) {
      var low = en.signal_score < 20 ? ' <span class="sig-low">(sig ' + en.signal_score + ')</span>' : '';
      var sel = '<select class="mem-type-sel" onchange="memChangeType(' + en.id + ', this.value)">' +
        MEMORY_TYPES.map(function(mt) { return '<option value="' + mt + '"' + (mt === t ? ' selected' : '') + '>' + memTypeLabel(mt) + '</option>'; }).join('') +
        '</select>';
      rows += '<div class="mem-entry"><span class="mem-entry-id">' + en.id + '</span>' +
        '<span class="mem-entry-text">' + esc(en.text) + low + '</span>' +
        '<span class="mem-entry-ops">' + sel +
        '<button class="mem-del-btn" onclick="memDelete(' + en.id + ')">del</button></span></div>';
    });
    if (!g.count) return;
    html += '<div class="mem-group"><div class="mem-group-hd" onclick="memToggleGroup(this)">' +
      '<span class="mem-group-arrow">▼</span><span>' + memTypeLabel(t) + '</span>' +
      '<span class="mem-group-count">' + g.count + ' · ' + g.chars + 'ch</span></div>' +
      '<div class="mem-group-bd">' + rows + (g.count > entries.length ? '<div class="mem-empty">… +' + (g.count - entries.length) + ' more not shown</div>' : '') + '</div></div>';
  });
  groupsEl.innerHTML = html || '<div class="mem-empty">No memory entries</div>';
  document.getElementById('memory-count').textContent = totalEntries;
  return totalEntries;
}

function memToggleGroup(hd) {
  var bd = hd.nextElementSibling;
  var arrow = hd.querySelector('.mem-group-arrow');
  bd.classList.toggle('closed');
  arrow.classList.toggle('closed');
}

function memDelete(id) {
  call('memory.delete', { entry_id: id, reason: 'user_request' }).then(function(r) {
    if (r && r.success) {
      showToast('ok', 'Memory #' + id + ' deleted (audit logged)');
      loadMemoryPanel();
    } else {
      showToast('err', (r && r.error && r.error.message) || 'Delete failed');
    }
  });
}

function memChangeType(id, newType) {
  call('memory.update', { entry_id: id, type: newType }).then(function(r) {
    if (r && r.success) {
      showToast('ok', 'Memory #' + id + ' changed to ' + newType);
      loadMemoryPanel();
    } else {
      showToast('err', (r && r.error && r.error.message) || 'Type change failed');
    }
  });
}

function loadMemoryPanel() {
  call('memory.list', {}).then(function(r) {
    // call() resolve 的是 JSON-RPC 的 msg.result（即 data 本体），不是 {result:...} 包装
    if (!r || !r.groups) {
      var g = document.getElementById('memory-groups');
      if (g) g.innerHTML = '<div class="mem-empty">Load failed — memory.list unavailable.</div>';
      return;
    }
    var data = r;
    var st = data.stats;
    document.getElementById('memory-stats').textContent =
      st.total_entries + ' entries · ' + st.total_chars + 'ch · ~' + st.total_tokens_est + ' tok · ' + st.usage_percent + '%';
    renderMemoryGroups(data);
    // diff 增删：对比上一次快照
    var newIds = {};
    MEMORY_TYPES.forEach(function(t) { data.groups[t].entries.forEach(function(en) { newIds[en.id] = en.text; }); });
    renderMemoryDiff(newIds);
    memorySnapshot = newIds;
  });
}
// === end P0-1 Memory ===

var plugins = [
  { id:'notes', icon:'<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.5 1.5 H9 L12.5 5 V14.5 H4.5 Z"/><path d="M9 1.5 V5 H12.5"/><path d="M6.5 8.5 H10 M6.5 11 H10 M6.5 13.5 H8.5"/></svg>', name:'Notes', desc:'Browse Obsidian notes' },
  { id:'project', icon:'<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1.5 4.5 V12 A1.5 1.5 0 0 0 3 13.5 H13 A1.5 1.5 0 0 0 14.5 12 V6.5 A1.5 1.5 0 0 0 13 5 H6.9 L5.3 3 H3 A1.5 1.5 0 0 0 1.5 4.5 Z"/></svg>', name:'Project', desc:'Project file browser' },
  { id:'terminal', icon:'<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="1.5" y="3" width="13" height="10" rx="1.5"/><path d="M4.5 6.5 L7 9 L4.5 11.5 M8 11.5 H11.5"/></svg>', name:'Terminal', desc:'Command history' },
  // TICKET-DESK-TEL：Telescope 引擎实况观测台 —— 图标细线 SVG（V2D25 TOOL_ICONS 同款风格，非 emoji）
  { id:'telescope', icon:'<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="4.6" cy="3.8" r="1.7"/><path d="M5.9 5.1 L11 10.9"/><circle cx="12.4" cy="12.2" r="2.4"/><path d="M12.8 14.6 l1.9-1.9 M11.7 13.8 l-1.7 1.7"/></svg>', name:'Telescope', desc:'Engine live view' },
];

function renderPluginList() {
  var el = document.getElementById('plugin-list');
  if (!el) return;
  el.innerHTML = plugins.map(function(p) {
    return '<div class="pitem" data-pid="' + p.id + '">' +
      '<span class="pi-icon">' + p.icon + '</span>' +
      '<div class="pi-body"><div class="pi-name">' + p.name + '</div><div class="pi-desc">' + p.desc + '</div></div>' +
      '<span class="pi-arrow">→</span></div>';
  }).join('');
  el.querySelectorAll('.pitem').forEach(function(item) {
    item.onclick = function() { openPlugin(item.dataset.pid); };
  });
}

function openPlugin(id) {
  var p = plugins.find(function(x) { return x.id === id; });
  if (!p) return;
  var panel = document.getElementById('right-panel');
  var tabs = document.getElementById('right-tabs');
  var content = document.getElementById('right-content');
  panel.classList.add('open');
  tabs.innerHTML = '<div class="rtab active">' + p.icon + ' ' + p.name + '<span class="close" onclick="closePanel()">✕</span></div>';
  // Adjust main width
  document.getElementById('main').style.maxWidth = 'calc(100vw - 240px - 340px)';
  // Plugin content
  if (id === 'notes') renderNotesPanel(content, _notesTree);
  else if (id === 'project') renderProjectPanel(content);
  else if (id === 'terminal') renderTerminalPanel(content);
  else if (id === 'telescope') renderTelescopePanel(content);
  else content.innerHTML = '<p style="color:var(--text-muted);margin-top:20px;text-align:center;">' + p.desc + '<br><br>Coming soon</p>';
}

function closePanel() {
  document.getElementById('right-panel').classList.remove('open');
  document.getElementById('main').style.maxWidth = '';
}

// ── Resizable right panel ──
(function() {
  var handle = document.getElementById('resize-handle');
  var panel = document.getElementById('right-panel');
  var mainEl = document.getElementById('main');
  if (!handle || !panel) return;
  var startX, startW;
  handle.addEventListener('mousedown', function(e) {
    startX = e.clientX;
    startW = panel.offsetWidth;
    handle.classList.add('active');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  });
  document.addEventListener('mousemove', function(e) {
    if (!handle.classList.contains('active')) return;
    var w = startW - (e.clientX - startX);
    if (w < 200) w = 200;
    if (w > 600) w = 600;
    panel.style.width = w + 'px';
    panel.style.minWidth = w + 'px';
    mainEl.style.maxWidth = 'calc(100vw - 240px - ' + w + 'px)';
  });
  document.addEventListener('mouseup', function() {
    handle.classList.remove('active');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });
})();

function renderNotesPanel(el, tree) {
  if (!tree || tree.length === 0) {
    el.innerHTML = '<p style="color:var(--text-muted);margin-top:20px;text-align:center;">Waiting for notes...</p>';
    return;
  }
  el.innerHTML = renderTree(tree, '');
}

function renderTree(nodes, prefix) {
  var html = '';
  nodes.forEach(function(n) {
    if (n.type === 'folder') {
      html += '<div class="nt-item folder">📁 ' + n.name + '</div>';
      html += '<div class="nt-children">' + renderTree(n.children || [], prefix + n.name + '/') + '</div>';
    } else {
      html += '<div class="nt-item file" onclick="showNote(\'' + esc(n.path) + '\')">📄 ' + n.name + '</div>';
    }
  });
  return html;
}

var _notesTree = null;

// Listen for notes.tree event from backend
on('notes.tree', function(payload) {
  _notesTree = (payload && payload.tree) || null;
  var content = document.getElementById('right-content');
  if (content && content.innerHTML.indexOf('nt-item') === -1) {
    renderNotesPanel(content, _notesTree);
  }
});

// Listen for notes.changed [DISABLED — auto-popup deferred to later fix]
/* on('notes.changed', function(payload) {
  if (!payload || !payload.file) return;
  var diff = (payload.diff || '').substring(0, 3000);
  var p = document.getElementById('right-panel');
  if (!p.classList.contains('open')) {
    openPlugin('notes');
  }
  var content = document.getElementById('right-content');
  var added = 0, removed = 0;
  if (diff) {
    diff.split('\n').forEach(function(l) {
      if (l.startsWith('+') && !l.startsWith('+++')) added++;
      else if (l.startsWith('-') && !l.startsWith('---')) removed++;
    });
  }
  var summary = esc(payload.file);
  if (diff) summary += ' — +' + added + ' / -' + removed + ' 行';
  else summary += ' — 已更新';
  // Load file content and render
  call('file.read', { filepath: payload.file }).then(function(r) {
    var body = '';
    if (r && r.content) {
      var txt = r.content;
      if (typeof txt === 'string' && txt.length > 10000) txt = txt.substring(0, 10000) + '\n...（截断）';
      body = md(txt);
    } else {
      body = '<p style="color:var(--text-muted);">无法加载文件内容</p>';
    }
    content.innerHTML = '<div style="margin-bottom:8px;">' +
      '<span onclick="renderNotesPanel(document.getElementById(\'right-content\'), _notesTree)" style="cursor:pointer;color:var(--text-muted);font-size:13px;">← 返回</span>' +
      '<span style="margin-left:8px;font-size:12px;color:var(--text2);">' + summary + '</span></div>' +
      body;
  });
}); */

// 票 P0-5：memory.changed 实时刷新 —— 面板打开则重载（快照对比 → diff 红删绿增
// 实时冒出）；未打开只更新导航 count，不打扰（吸取 notes.changed 自动弹窗教训）。
on('memory.changed', function(payload) {
  if (!payload) return;
  var mv = document.getElementById('memory-view');
  var open = mv && mv.style.display !== 'none';
  if (open) {
    loadMemoryPanel();
  } else {
    call('memory.list', {}).then(function(r) {
      if (r && r.stats) {
        var c = document.getElementById('memory-count');
        if (c) c.textContent = r.stats.total_entries;
      }
    });
  }
});

// ── Project Plugin ──
var _projectTree = null;

function renderProjectPanel(el) {
  if (_projectTree && _projectTree.length > 0) {
    el.innerHTML = '<div style="margin-bottom:8px;display:flex;align-items:center;gap:4px;">' +
      '<span style="font-size:12px;color:var(--text2);flex:1;">📁 Project</span>' +
      '<span onclick="importProject()" style="cursor:pointer;font-size:11px;color:var(--text-muted);">Change</span>' +
      '<span onclick="clearProject()" style="cursor:pointer;font-size:13px;color:var(--text-muted);margin-left:4px;">✕</span></div>' +
      renderProjectTree(_projectTree);
    return;
  }
  el.innerHTML = '' +
    '<div style="text-align:center;margin-top:40px;">' +
    '<p style="font-size:13px;color:var(--text2);margin-bottom:8px;">📁 Import project folder</p>' +
    '<p style="font-size:11px;color:var(--text-muted);margin-bottom:20px;">Choose a project folder; Bobo will browse its files</p>' +
    '<button onclick="importProject()" style="padding:10px 24px;border-radius:8px;border:1px solid var(--border);background:var(--bg2);color:var(--text);cursor:pointer;font:inherit;font-size:13px;">Import from Mac</button>' +
    '</div>';
}

function clearProject() {
  _projectTree = null;
  var content = document.getElementById('right-content');
  renderProjectPanel(content);
}

// ── Terminal Plugin ──
var _terminalLogs = [];
var _terminalEl = null;

function renderTerminalPanel(el) {
  _terminalEl = el;
  if (_terminalLogs.length === 0) {
    el.innerHTML = '<div style="text-align:center;margin-top:40px;">' +
      '<p style="font-size:13px;color:var(--text2);margin-bottom:8px;">⚡ Terminal</p>' +
      '<p style="font-size:11px;color:var(--text-muted);">Commands Bobo runs will appear here</p></div>';
    return;
  }
  var html = '<div style="margin-bottom:8px;display:flex;align-items:center;gap:4px;">' +
    '<span style="font-size:12px;color:var(--text2);flex:1;">⚡ Terminal</span>' +
    '<span onclick="clearTerminal()" style="cursor:pointer;font-size:11px;color:var(--text-muted);">Clear</span></div>';
  _terminalLogs.forEach(function(log) {
    // F4-5: 终端面板长输出拦截 —— 超 2000 字符显示开头预览 + "显示全部/收起"按钮
    var outText = log.output || '';
    var isLong = outText.length > 2000;
    var shown = isLong ? outText.substring(0, 2000) + '\n... (output truncated, ' + outText.length + ' chars)' : outText;
    html += '<div style="margin-bottom:8px;">' +
      '<div style="font-family:monospace;font-size:11px;color:var(--text2);padding:2px 0;">$ ' + esc(log.command) + '</div>' +
      '<div style="font-family:monospace;font-size:11px;color:var(--text2);white-space:pre-wrap;padding:4px 8px;background:var(--bg2);border-radius:4px;">' + esc(shown) + '</div>' +
      (isLong ? '<button onclick="toggleTerminalOutput(this)" data-expanded="0" data-idx="' + _terminalLogs.indexOf(log) + '" style="margin-top:4px;padding:2px 10px;border-radius:4px;border:1px solid var(--border);background:var(--bg3);color:var(--text2);cursor:pointer;font-family:inherit;font-size:11px;">Show all (' + outText.length + ' chars)</button>' : '') +
      '</div>';
  });
  el.innerHTML = html;
  el.scrollTop = el.scrollHeight;
}

// F4-5: 终端长输出展开/收起切换（按钮内联在日志块下方）
function toggleTerminalOutput(btn) {
  var idx = parseInt(btn.getAttribute('data-idx'), 10);
  var log = _terminalLogs[idx];
  if (!log) return;
  var expanded = btn.getAttribute('data-expanded') === '1';
  var outText = log.output || '';
  var shown = expanded ? outText.substring(0, 2000) + '\n... (output truncated, ' + outText.length + ' chars)' : outText;
  btn.setAttribute('data-expanded', expanded ? '0' : '1');
  btn.textContent = expanded ? 'Show all (' + outText.length + ' chars)' : 'Collapse';
  var block = btn.previousElementSibling;
  if (block) block.textContent = shown;
}

on('terminal.output', function(payload) {
  if (isForeignSession(payload)) return;
  if (!payload || !payload.command) return;
  _terminalLogs.push({ command: payload.command, output: payload.output || '' });
  if (_terminalLogs.length > 100) _terminalLogs.shift();
  if (_terminalEl) renderTerminalPanel(_terminalEl);
});

function clearTerminal() {
  _terminalLogs = [];
  if (_terminalEl) renderTerminalPanel(_terminalEl);
}

function renderProjectTree(nodes) {
  var html = '';
  nodes.forEach(function(n) {
    if (n.type === 'folder') {
      html += '<div class="nt-item folder">📁 ' + n.name + '</div>';
      html += '<div class="nt-children">' + renderProjectTree(n.children || []) + '</div>';
    } else {
      html += '<div class="nt-item file" onclick="showProjectFile(\'' + esc(n.path) + '\')">📄 ' + n.name + '</div>';
    }
  });
  return html;
}

function importProject() {
  if (!window.boboAPI || !window.boboAPI.selectFolder) return;
  window.boboAPI.selectFolder().then(function(path) {
    if (!path) return;
    call('project.set_root', { path: path, session_id: currentSessionId }).then(function(r) {
      if (r && r.error) { alert(r.error); return; }
    });
  });
}

// Listen for project.tree from backend
on('project.tree', function(payload) {
  if (!payload) return;
  _projectTree = payload.tree || [];
  // Refresh the panel if it's open
  var content = document.getElementById('right-content');
  var parentEl = content && content.closest ? content.closest('#right-panel') : null;
  if (parentEl && parentEl.classList.contains('open') && content && content.innerHTML.indexOf('nt-item') === -1) {
    renderProjectPanel(content);
  }
});

function showProjectFile(filepath, full) {
  var content = document.getElementById('right-content');
  var backBtn = '<span onclick="renderProjectPanel(document.getElementById(\'right-content\'))" style="cursor:pointer;color:var(--text-muted);font-size:13px;">← Back</span>';
  content.innerHTML = '<div style="margin-bottom:10px;">' + backBtn + '<span style="margin-left:8px;font-size:12px;color:var(--text2);">' + esc(filepath) + '</span></div><p style="color:var(--text-muted);">Loading...</p>';
  call('file.read', { filepath: filepath }).then(function(r) {
    if (r && r.content) {
      var txt = r.content;
      // F2-4: 原始输出默认收起 —— 超 2000 字符只显示开头预览 + "显示全部"按钮
      // （owner 截图实证：原始代码倾泻占屏是层级倒置；"原始输出收起"为裁决原则）
      if (typeof txt === 'string' && txt.length > 2000 && !full) {
        var preview = txt.substring(0, 2000) + '\n\n... (raw output too long, collapsed)';
        var showAll = '<div style="margin-top:10px;"><button onclick="showProjectFile(\'' + esc(filepath) + '\', true)" style="padding:6px 14px;border-radius:6px;border:1px solid var(--border);background:var(--bg3);color:var(--text);cursor:pointer;font-family:inherit;font-size:12px;">Show all (' + txt.length + ' chars)</button></div>';
        content.innerHTML = '<div style="margin-bottom:10px;">' + backBtn + '<span style="margin-left:8px;font-size:12px;color:var(--text2);">' + esc(filepath) + '</span></div>' + md(preview) + showAll;
      } else {
        if (typeof txt === 'string' && txt.length > 10000) txt = txt.substring(0, 10000) + '\n... (truncated to 10000 chars)';
        content.innerHTML = '<div style="margin-bottom:10px;">' + backBtn + '<span style="margin-left:8px;font-size:12px;color:var(--text2);">' + esc(filepath) + '</span></div>' + md(txt);
      }
    } else {
      content.innerHTML = '<div style="margin-bottom:10px;">' + backBtn + '</div><p style="color:var(--text-muted);">Failed to load file</p>';
    }
  });
}

function showNote(filepath, full) {
  var content = document.getElementById('right-content');
  var backBtn = '<span onclick="renderNotesPanel(document.getElementById(\'right-content\'), _notesTree)" style="cursor:pointer;color:var(--text-muted);font-size:13px;">← Back</span>';
  content.innerHTML = '<div style="margin-bottom:10px;">' + backBtn + '<span style="margin-left:8px;font-size:12px;color:var(--text2);">' + esc(filepath) + '</span></div><div class="np"><p style="color:var(--text-muted);">Loading...</p></div>';
  call('file.read', { filepath: filepath }).then(function(r) {
    if (r && r.content) {
      var txt = r.content;
      // F2-4: 原始输出默认收起（与 showProjectFile 同原则）
      if (typeof txt === 'string' && txt.length > 2000 && !full) {
        var preview = txt.substring(0, 2000) + '\n\n... (raw output too long, collapsed)';
        var showAll = '<div style="margin-top:10px;"><button onclick="showNote(\'' + esc(filepath) + '\', true)" style="padding:6px 14px;border-radius:6px;border:1px solid var(--border);background:var(--bg3);color:var(--text);cursor:pointer;font-family:inherit;font-size:12px;">Show all (' + txt.length + ' chars)</button></div>';
        content.innerHTML = '<div style="margin-bottom:10px;">' + backBtn + '<span style="margin-left:8px;font-size:12px;color:var(--text2);">' + esc(filepath) + '</span></div><div class="np">' + md(preview) + '</div>' + showAll;
      } else {
        if (typeof txt === 'string' && txt.length > 10000) txt = txt.substring(0, 10000) + '\n... (truncated to 10000 chars)';
        content.innerHTML = '<div style="margin-bottom:10px;">' + backBtn + '<span style="margin-left:8px;font-size:12px;color:var(--text2);">' + esc(filepath) + '</span></div>' + md(txt);
      }
    } else {
      content.innerHTML = '<div style="margin-bottom:10px;">' + backBtn + '</div><p style="color:var(--text-muted);">Failed to load file</p>';
    }
  });
}
