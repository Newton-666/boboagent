// ── Input ──────────────────────────────────────────────────────────────
// 票 P0-1 改版：New chat 按钮已提升为侧栏导航项 New session（onNavNewSession），
// 旧按钮 #new-chat 已移除，绑定随之删除（防止 getElementById 空引用中断后续 JS）。

// TICKET-DESK-V4: 小组件开关（侧栏按钮 ↔ /widget 命令 ↔ 持久化 三向同步同源）
// 真实窗口状态以主进程为准（widget-toggle IPC 返回），本地按钮只投影主进程状态。
var widgetBtn = document.getElementById('widget-toggle');
function syncWidgetBtn(enabled) {
  if (!widgetBtn) return;
  widgetBtn.classList.toggle('on', !!enabled);
  widgetBtn.textContent = enabled ? 'Widget ✓' : 'Widget';
  widgetBtn.title = enabled ? 'Close live widget' : 'Open live widget (read-only)';
}
function widgetToggle() {
  if (window.boboAPI && window.boboAPI.widgetToggle) {
    window.boboAPI.widgetToggle().then(function(r) {
      syncWidgetBtn(r && r.enabled);
      addStatus(r && r.enabled ? 'Live widget opened (read-only)' : 'Live widget closed');
    });
  } else {
    addStatus('Live widget is desktop-only (not available in browser mode)');
  }
}
if (widgetBtn) widgetBtn.addEventListener('click', widgetToggle);
// 启动恢复按钮态（默认关；真实状态以主进程持久化配置为准）
if (window.boboAPI && window.boboAPI.widgetStatus) {
  window.boboAPI.widgetStatus().then(function(r) { syncWidgetBtn(r && r.enabled); });
}
// TICKET-DESK-V4: 审批联动落地 —— 小窗点击 → 主进程唤起主窗 → 这里跳对应会话（现成 loadSession）
if (window.boboAPI && window.boboAPI.onWidgetFocusSession) {
  window.boboAPI.onWidgetFocusSession(function(sid) {
    if (sid && sid !== currentSessionId) loadSession(sid);
  });
}
// TICKET-DESK-V4B: 小窗钉选变化（点击会话名轮换/回落）→ 主窗同步行内按钮态（三向一致）
if (window.boboAPI && window.boboAPI.onWidgetPinChanged) {
  window.boboAPI.onWidgetPinChanged(function(sid) {
    _widgetPinnedSid = sid || null;
    renderSessions();
  });
}

function handleSlash(cmd) {
  if (cmd === 'help') { addMsg('bobo', '**Available commands:**\n- /help — show help\n- /clear — clear current chat\n- /undo — undo last step\n- /tools — list tools\n- /settings — view config\n- /widget — toggle live widget\n\nOr say \"switch to OpenAI\" to change model', 'help-'+Date.now()); return true; }
  if (cmd === 'clear') { clearChat(); welcomeEl.style.display = 'flex'; addStatus('Chat cleared'); return true; }
  if (cmd === 'tools') {
    call('tools.list', {}).then(function(r) {
      var tools = r.tools || [];
      var names = tools.map(function(t){return t.name;}).join(', ');
      addMsg('bobo', '**Available tools (' + tools.length + '):**\n' + names, 'tools-'+Date.now());
    });
    return true;
  }
  if (cmd === 'settings') {
    call('config.full', {}).then(function(r) {
      addMsg('bobo', '**Current config:**\n```json\n' + JSON.stringify(r.config, null, 2) + '\n```', 'cfg-'+Date.now());
    });
    return true;
  }
  if (cmd === 'undo') { addStatus('Use Ctrl+Z or /undo in TUI'); return true; }
  // TICKET-DESK-V4: /widget 本地命令 —— 与侧栏开关同源（同一 widgetToggle 入口）
  if (cmd === 'widget') { widgetToggle(); return true; }
  return false;
}

// TICKET-DESK-V2B3：斜杠命令路由 + "/" 命令面板
// 数据源：后端 commands.catalog（commands 结构 + descs 说明字段，只读，启动拉一次）
var slashPanelEl = document.getElementById('slash-panel');
var slashCommands = [];
var slashSel = -1;

function execSlash(cmd) {
  // V2B3 斜杠路由：未本地处理的 "/" 输入一律走后端 slash.exec（携带 session_id），
  // 结果显示为系统消息（.status），不进 LLM
  if (!connected || !currentSessionId) { addStatus('Command not run: not connected or no session'); return; }
  call('slash.exec', { command: cmd, session_id: currentSessionId }).then(function(r) {
    if (r && r.output) { addStatus(r.output); }
    else if (r && r.error) { addStatus('Command failed: ' + r.error); }
  });
}

function loadSlashCatalog() {
  call('commands.catalog', {}).then(function(r) {
    var cmds = (r && r.commands) || {};
    var descs = (r && r.descs) || {};
    slashCommands = [];
    Object.keys(cmds).forEach(function(group) {
      var items = cmds[group] || {};
      Object.keys(items).forEach(function(name) {
        slashCommands.push({ name: name, usage: items[name], desc: descs[name] || '' });
      });
    });
  });
}

function slashFilter(q) {
  var kw = (q || '').slice(1).toLowerCase();
  var out = [];
  if (!slashCommands.length) return out;
  for (var i = 0; i < slashCommands.length; i++) {
    var c = slashCommands[i];
    var n = c.name.toLowerCase();
    if (!kw || n.indexOf('/' + kw) === 0 || n.indexOf(kw) >= 0) {
      out.push(c);
      if (out.length >= 8) break;
    }
  }
  return out;
}

function hideSlashPanel() {
  if (slashPanelEl) slashPanelEl.style.display = 'none';
  slashSel = -1;
}

function renderSlashPanel(q) {
  if (!slashPanelEl) return;
  var list = slashFilter(q);
  if (!list.length) { hideSlashPanel(); return; }
  if (slashSel < 0) slashSel = 0;
  if (slashSel >= list.length) slashSel = list.length - 1;
  slashPanelEl.innerHTML = list.map(function(c, i) {
    return '<div class="sp-item' + (i === slashSel ? ' sp-active' : '') + '" data-idx="' + i + '">' +
      '<span class="sp-name">' + esc(c.name) + '</span>' +
      '<span class="sp-desc">' + esc(c.desc || c.usage || '') + '</span></div>';
  }).join('');
  slashPanelEl.style.display = 'block';
}

function moveSlashSel(d) {
  var list = slashFilter(inputEl.value);
  if (!list.length) return;
  slashSel += d;
  if (slashSel < 0) slashSel = 0;
  if (slashSel >= list.length) slashSel = list.length - 1;
  // 只更新高亮 class，不整表重绘（防闪烁）
  var items = slashPanelEl.querySelectorAll('.sp-item');
  for (var i = 0; i < items.length; i++) {
    items[i].className = 'sp-item' + (i === slashSel ? ' sp-active' : '');
  }
}

function acceptSlashSel() {
  // Enter/Tab/点击：把选中命令补全进输入框（不自动发送，便于追加参数），光标移到末尾
  var list = slashFilter(inputEl.value);
  if (!list.length || slashSel < 0) return;
  var full = list[slashSel].name;
  inputEl.value = full + ' ';
  var len = inputEl.value.length;
  try { inputEl.setSelectionRange(len, len); } catch (e) {}
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 200) + 'px';
  hideSlashPanel();
  inputEl.focus();
}

slashPanelEl.addEventListener('mouseover', function(e) {
  var t = e.target;
  while (t && t !== slashPanelEl && !(t.classList && t.classList.contains('sp-item'))) t = t.parentNode;
  if (t && t.classList && t.classList.contains('sp-item')) {
    var idx = parseInt(t.getAttribute('data-idx'), 10);
    if (idx !== slashSel) moveSlashSel(idx - slashSel);
  }
});
slashPanelEl.addEventListener('click', function(e) {
  var t = e.target;
  while (t && t !== slashPanelEl && !(t.classList && t.classList.contains('sp-item'))) t = t.parentNode;
  if (t && t.classList && t.classList.contains('sp-item')) {
    slashSel = parseInt(t.getAttribute('data-idx'), 10);
    acceptSlashSel();
  }
});

// TICKET-GUI-F1 (F1-1): 输入法组词标志 —— 组词中任何回车/发送都不触发，交给 IME 上屏
var imeComposing = false;
inputEl.addEventListener('compositionstart', function() { imeComposing = true; });
inputEl.addEventListener('compositionend', function() { imeComposing = false; });

sendEl.addEventListener('click', function() {
  // F1-1: 输入法组词中点发送按钮 → 拦截（半成品拼音不上屏）
  if (imeComposing) return;
  var text = inputEl.value.trim(); var img = pendingImage;
  if ((!text && !img) || !connected || messaging) return;
  inputEl.value = '';
  inputEl.style.height = 'auto';
  hideSlashPanel();
  if (text.startsWith('/')) {
    // TICKET-DESK-V2B3：斜杠路由 —— 本地快速命令（clear 需清 UI）走 handleSlash；
    // 其余一律走后端 slash.exec（携带 session_id），结果显示为系统消息，不再进 LLM
    if (handleSlash(text.slice(1))) return;
    execSlash(text.slice(1));
    return;
  }
  // TICKET-VISION-CHAT-UPLOAD：图文一条消息（图片在上，文字在下）
  addMsg('user', text, 'user-' + Date.now(), false, img);
  sendPrompt(text, img);
});
// F2-2 + F4-6: AUTO 开关 —— 复用后端现有 slash.exec /auto 通道（翻转会话级 AUTO MODE）。
// F4-6 修复：必须携带 session_id —— 否则后端 handle_slash_exec 取到空串 sid，
// 翻转的是 auto_mode[""]，真实会话从未进入 AUTO → engine 走 confirm_callback 弹窗
// （UI 显示 AUTO ✓ 与后端真实状态裂脑，即"GUI 无脑弹窗"根因）。
// 携带 session_id 后与 TUI /auto 完全对齐：AUTO 会话零弹窗、红线自动拒绝留痕。
document.getElementById('auto-toggle').addEventListener('click', function() {
  if (!connected || !currentSessionId) return;
  call('slash.exec', { command: 'auto', session_id: currentSessionId }).then(function(r) {
    if (r && r.output) addStatus(r.output);
  });
});
// TICKET-COMPUTER-USE-ROUTE：COMPUTER use 开关 —— 复用后端 slash.exec /computer-use 通道
// （翻转会话级 computer use 模式：界面/搜索/操作类任务优先 computer_use 快速直接）
document.getElementById('computer-use-toggle').addEventListener('click', function() {
  if (!connected || !currentSessionId) return;
  call('slash.exec', { command: 'computer-use', session_id: currentSessionId }).then(function(r) {
    if (r && r.output) addStatus(r.output);
  });
});
inputEl.addEventListener('keydown', function(e) {
  // F1-1: 组词中（isComposing / keyCode 229 / imeComposing 任一命中）回车不发送，上屏选词交给输入法
  if (e.isComposing || e.keyCode === 229 || imeComposing) return;
  // TICKET-DESK-V2B3：命令面板键（↑↓ 选择 / Enter|Tab 补全 / Esc 关闭）——
  // 位于 IME 守卫之后，组词中绝不触发面板操作
  var spOpen = slashPanelEl && slashPanelEl.style.display !== 'none';
  if (spOpen) {
    if (e.key === 'ArrowDown') { e.preventDefault(); moveSlashSel(1); return; }
    if (e.key === 'ArrowUp') { e.preventDefault(); moveSlashSel(-1); return; }
    if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); acceptSlashSel(); return; }
    if (e.key === 'Escape') { e.preventDefault(); hideSlashPanel(); return; }
  }
  if (e.key === 'Enter') {
    // F2-1: Shift+回车 = 换行（textarea 默认插入 \n，不拦截）
    if (e.shiftKey) return;
    // F2-1: ⌘/Ctrl+回车 = 发送的兼容别名（保留旧习惯）
    if (e.metaKey || e.ctrlKey) { e.preventDefault(); sendEl.click(); return; }
    // F2-1: 回车 = 发送（标准聊天客户端语义）
    e.preventDefault(); sendEl.click();
  }
});
// Auto-height textarea
inputEl.addEventListener('input', function() {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 200) + 'px';
  // TICKET-DESK-V2B3：首字符 "/" 弹命令面板（实时过滤；组词中不弹）
  if (this.value.charAt(0) === '/' && connected && !imeComposing) renderSlashPanel(this.value);
  else hideSlashPanel();
  // TICKET-VISION-CHAT-UPLOAD：草稿（text）随输入实时存 localStorage（按会话）
  if (currentSessionId) saveDraft(currentSessionId);
});
