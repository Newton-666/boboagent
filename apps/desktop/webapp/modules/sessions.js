// ── Sessions ───────────────────────────────────────────────────────────
async function loadSessions() {
  var result = await call('session.list');
  if (result && result.sessions) {
    sessions = result.sessions;
    renderSessions();
    var c = document.getElementById('session-count');
    if (c) c.textContent = sessions.length;
  }
  // 票 P0-1：连接就绪后顺带加载 Memory 面板数据（填充 count + 首次快照）
  loadMemoryPanel();
  // 票 TICKET-SKILL-PANEL v2：连接就绪后加载 Skills 计数（填充左侧栏 badge）
  loadSkillsPanel();
}
function startRename(s, span) {
  var input = document.createElement('input');
  input.value = s.title || '';
  input.style.width = '100%'; input.style.border = 'none'; input.style.outline = 'none';
  input.style.background = 'transparent'; input.style.font = 'inherit'; input.style.color = 'inherit';
  span.textContent = '';
  span.appendChild(input);
  input.focus();
  input.select();
  function save() {
    var t = input.value.trim();
    if (t && t !== s.title) {
      s.title = t.substring(0, 35);
      // TICKET-GUI-F7：手动改名成功 → 本地立即标 user_named=true（防自动命名覆盖）
      s.user_named = true;
      call('session.rename', { session_id: s.id, title: t });
      renderSessions();
      // TICKET-DESK-V2A：重命名成功 toast 接入点
      showToast('success', 'Renamed');
    } else {
      span.textContent = s.title || s.id;
    }
  }
  input.onblur = save;
  input.onkeydown = function(e) {
    if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
    if (e.key === 'Escape') { span.textContent = s.title || s.id; }
  };
}
function renderSessions(filter) {
  sessionListEl.innerHTML = '';
  var filtered = sessions;
  if (filter) {
    var q = filter.toLowerCase();
    filtered = sessions.filter(function(s) { return (s.title || '').toLowerCase().indexOf(q) !== -1; });
  }
  if (filtered.length === 0) {
    // TICKET-DESK-V2A：无结果/无会话统一空态（EmptyState 组件，配色取现有色板）
    var empty = document.createElement('div');
    empty.className = 'v2a-empty';
    empty.innerHTML = '<div class="v2a-empty-icon">' + (filter ? '🔍' : '🗂') + '</div><div>' + (filter ? 'No matches' : 'No sessions yet — start a new chat') + '</div>';
    sessionListEl.appendChild(empty);
    return;
  }
  // TICKET-DESK-V2A：pin 置顶会话排最前，其余保持原序（稳定排序）
  filtered.sort(function(a, b) { return (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0); });
  filtered.forEach(function(s) {
    // TICKET-GUI-F3 (F3-1/F3-2): data-sid 供加载指示定位；active 类严格跟随 currentSessionId
    var div = document.createElement('div'); div.className = 'session-item' + (s.id===currentSessionId?' active':''); div.dataset.sid = s.id;
    var span = document.createElement('span'); span.textContent = s.title || s.id; span.className = 'stitle';
    // TICKET-GUI-F10（加分项）：后台活动中圆点指示（弱色取色板 --text-muted，标题前；
    // 样式走内联 style —— V2A/V2B CSS 零改动闸门约束，不新增全局 CSS 规则）
    if (bgActiveSids[s.id]) {
      var bgDot = document.createElement('span'); bgDot.className = 'bg-active-dot'; bgDot.title = 'Running in background';
      bgDot.style.cssText = 'width:6px;height:6px;border-radius:50%;background:var(--text-muted);display:inline-block;margin-right:6px;flex-shrink:0;';
      span.insertBefore(bgDot, span.firstChild);
    }
    span.onclick = function() { loadSession(s.id); };
    // V2A 打磨：pin 标记改细 SVG 弱色图钉（弃用 emoji 图钉，渲染大红太扎眼）
    if (s.pinned) {
      var pinMark = document.createElement('span'); pinMark.className = 'pin-mark';
      pinMark.innerHTML = PIN_SVG;
      span.insertBefore(pinMark, span.firstChild);
    }
    // V2A 打磨：行内三键统一 .act（同尺寸同基线紧凑右置），顺序 pin→改名→删除
    var pin = document.createElement('button'); pin.className = 'act pin' + (s.pinned ? ' on' : ''); pin.innerHTML = PIN_SVG; pin.title = s.pinned ? 'Unpin' : 'Pin';
    pin.onclick = function(e) { e.stopPropagation(); togglePin(s); };
    var re = document.createElement('button'); re.className = 'act re'; re.textContent = '✎'; re.title = 'Rename';
    re.onclick = function(e) { e.stopPropagation(); startRename(s, span); };
    var del = document.createElement('button'); del.className = 'act del'; del.textContent = '✕'; del.title = 'Delete';
    del.onclick = function(e) { e.stopPropagation(); deleteSession(s.id); };
    // TICKET-DESK-V4B：行内四键统一 .act（顺序 pin→改名→删除→投影到小组件；on 态亮品牌橙）
    var proj = document.createElement('button'); proj.className = 'act proj' + (_widgetPinnedSid === s.id ? ' on' : ''); proj.innerHTML = PROJECT_SVG; proj.title = 'Project to widget';
    proj.onclick = function(e) { e.stopPropagation(); widgetPinSession(_widgetPinnedSid === s.id ? '' : s.id); };
    div.appendChild(span); div.appendChild(pin); div.appendChild(re); div.appendChild(del); div.appendChild(proj);
    sessionListEl.appendChild(div);
  });
  // TICKET-DESK-V4B：会话列表广播给小窗（会话名映射 + 钉住会话被删时小窗回落兜底）
  if (typeof window !== 'undefined' && window.boboAPI && window.boboAPI.widgetSessions) {
    window.boboAPI.widgetSessions(sessions.map(function(x) { return { id: x.id, title: x.title || x.id }; }));
  }
}
// V2A 打磨：细线 SVG 图钉（替代 📌 emoji，视觉克制）
var PIN_SVG = '<svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M9.6 1.2l5.2 5.2-1.1 1.1-1.7-.4-2.7 2.7.4 3.6-1.1 1.1L5.5 11.4l-3.6 3.6-.7-.7 3.6-3.6-3.1-3.1 1.1-1.1 3.6.4 2.7-2.7-.4-1.7z"/></svg>';
// TICKET-DESK-V2A：pin 切换（本地即时渲染 + 后端持久化；失败静默，下次 list 回源）
function togglePin(s) {
  s.pinned = !s.pinned;
  call('session.pin', { session_id: s.id, pinned: s.pinned });
  renderSessions(document.getElementById('session-search').value);
}

// TICKET-DESK-V2A：行内删除 → 二次确认模态（复用 approval 样式体系）+ 成功 toast
function deleteSession(sid) {
  askConfirm('⚠ Delete session', 'Delete this session? It will also be removed in TUI.', function() { doDeleteSession(sid); });
}
async function doDeleteSession(sid) {
  await call('session.delete', { session_id: sid });
  sessions = sessions.filter(function(s) { return s.id !== sid; });
  showToast('success', 'Session deleted');
  // TICKET-DESK-V4B：删的是小窗钉住的会话 → 自动回落跟随主窗（不留僵尸投影）
  if (_widgetPinnedSid === sid) widgetPinSession('');
  var wasCurrent = currentSessionId === sid;
  if (wasCurrent) {
    // F3-1: 删除当前会话后落到第一个会话 —— 完整 loadSession（内容区与高亮同步切换）
    currentSessionId = null;
    clearChat(); welcomeEl.style.display = 'flex';
    if (sessions.length > 0) {
      await loadSession(sessions[0].id);
    } else {
      renderSessions();
      // V4B: 当前会话清空广播（小窗跟随模式基准复位）
      if (typeof window !== 'undefined' && window.boboAPI && window.boboAPI.widgetCurrentSession) {
        window.boboAPI.widgetCurrentSession('', '');
      }
    }
  } else {
    renderSessions();
  }
}
function updateSessionTitle(sid, text) {
  var s = sessions.find(function(x) { return x.id === sid; });
  // TICKET-GUI-F7：手动命名标记为真则拒绝自动覆盖（双保险，防其他自动路径）
  if (s && !s.user_named) {
    s.title = (text || s.title).substring(0, 35);
    renderSessions();
    // TICKET-GUI-F11：自动命名走持久化通道（auto=true 落盘但不置 user_named；
    // 已 user_named 的会话后端拒绝覆盖）—— 重启后标题不丢，TUI 读同一文件同步
    call('session.rename', { session_id: sid, title: s.title, auto: true });
  }
}

// TICKET-GUI-F3 重写：F3-1 选中态立即跟随 currentSessionId（单一事实源）；
// F3-2 点击必应答（立即加载指示、失败显式报错、连点以后一次为准）；
// F3-3 历史全文恢复（归档 archived_messages 拼接 + 压缩分隔线）。
async function loadSession(sid) {
  // 票 P0-1 改版：点会话自动关 Memory 主面板，回到正常聊天区；
  // TICKET-SKILL-PANEL v2 扩展：hideAllViews 一并覆盖 skills 等其它视图（互斥）
  hideAllViews();
  showInputBox();  // 恢复输入框（hideAllViews 已隐藏；回到聊天区必须能输入）
  // 回到聊天区：chat 显示、welcome 隐藏（原 closeMemoryView→showMainChat 语义；
  // hideAllViews 只隐藏视图不显示 chat，这里必须补显示）
  var _w = document.getElementById('welcome');
  var _c = document.getElementById('chat');
  if (_w) _w.style.display = 'none';
  if (_c) _c.style.display = '';
  setView('');
  // F3-1: 点击立即同步选中态（不等 resume 返回，杜绝高亮脱节）
  if (currentSessionId !== sid) {
    // TICKET-GUI-F13：离开当前会话前，把现场展开姿势落盘（重启回放按姿势还原）
    if (currentSessionId) { recordPose(currentSessionId); saveDraft(currentSessionId); }
    currentSessionId = sid;
    renderSessions();
    renderBusyUI();   // V4B⓪：切会话立即按新会话忙碌态刷新输入区/状态条/停止键
    restoreDraft(sid);  // TICKET-VISION-CHAT-UPLOAD：还原该会话草稿（图+文）
  }
  // F3-2 竞态：本次加载序号；期间再点其他会话，本次结果作废
  var mySeq = ++sessionLoadSeq;
  setSessionLoading(sid, true);
  addStatus('Loading session…');
  var result = null;
  try {
    result = await call('session.resume', { session_id: sid });
  } catch (e) {
    result = null;
  }
  if (mySeq !== sessionLoadSeq) return; // 已被后一次点击作废
  setSessionLoading(sid, false);
  if (!result || result.error || !result.session_id) {
    // F3-2: 失败必须显式报错，禁止静默停留旧会话
    // TICKET-GUI-F25：真实后端 err 显示真实消息（errMsg 提取）；超时/断连
    // （resolve({}) → errMsg 'unknown'）保持原语义提示 unresponsive
    var em = errMsg(result);
    if (em === 'unknown') em = 'Backend unresponsive (timeout or disconnected)';
    addStatus('⚠ Failed to load session: ' + em);
    return;
  }
  clearChat();
  // 竞态防护：用户已在 await 期间切到 memory/skills → 恢复该视图的显示状态
  // （clearChat 会把 welcome 设 flex，切走时必须把 welcome 压回去，防叠层）
  if (_activeView !== '') {
    var _w3 = document.getElementById('welcome');
    if (_w3) _w3.style.display = 'none';
  }
  // TICKET-GUI-F24：切会话回显该会话已保存的 request（无则空面板——不串）
  reqSyncFromSession(result.request);
  // TICKET-GUI-F13：长会话（现存消息 > HIST_WINDOW_THRESHOLD）走窗口化惰性渲染
  //（DOM 节点硬上限 + 占位高度精确）；短会话走 renderFullHistory 全量（零变化）
  var msgsLen = (result.messages || []).length;
  if (msgsLen > HIST_WINDOW_THRESHOLD) {
    await renderFullHistoryWindowed(sid, result);
  } else {
    // F3-3: 归档全文 + 现存消息拼接，压缩边界给分隔线
    await renderFullHistory(sid, result);
  }
  chatEl.scrollTop = chatEl.scrollHeight;
  // 会话有历史消息 → 隐藏 welcome 欢迎页，显示 chat 聊天区（clearChat 会把
  // welcome 设为 flex，渲染完历史后必须切回 chat；否则 welcome 叠在消息上）
  // 竞态防护：用户已在 await 期间切到 memory/skills（_activeView 非空）→
  // 不抢回 chat（修复：点 session 后立刻点 memory，loadSession 返回不再覆盖）
  if (msgsLen > 0 && _activeView === '') {
    var _w2 = document.getElementById('welcome');
    var _c2 = document.getElementById('chat');
    if (_w2) _w2.style.display = 'none';
    if (_c2) _c2.style.display = '';
  }
  // F2-2: 会话恢复时同步 AUTO 开关状态（session.resume 返回 auto_state，真实后端状态）
  setMode(result.auto_state ? 'auto' : '');
  // TICKET-COMPUTER-USE-ROUTE：会话恢复时同步 COMPUTER use 开关状态（resume 返回 computer_use_state）
  (function(){ var cut = document.getElementById('computer-use-toggle'); if (cut) { cut.classList.toggle('on', !!result.computer_use_state); cut.textContent = result.computer_use_state ? 'COMPUTER ✓' : 'COMPUTER'; } })();
  call('session.activate', { session_id: sid });
  // TICKET-GUI-F10：切回即清"后台活动中"标记（resume 全量已拉取，圆点无意义）
  clearBgActive(sid);
  renderSessions();
  renderBusyUI();   // V4B⓪：resume 完成后按新会话忙碌态最终刷新一次（兜底 gateway.ready 预赋值路径）
  // TICKET-DESK-V4B：当前会话广播给小窗（跟随模式对照基准；title 供会话指示显示）
  if (typeof window !== 'undefined' && window.boboAPI && window.boboAPI.widgetCurrentSession) {
    var cur = sessions.find(function(x) { return x.id === sid; });
    window.boboAPI.widgetCurrentSession(sid, cur ? (cur.title || sid) : sid);
  }
  // Update title with first user message
  // TICKET-GUI-F7：自动命名闸门 —— 用户手动命名过（user_named=true）则不覆盖；
  // 未手动命名的会话仍保留自动取名行为
  var msgs = result.messages || [];
  var firstUserMsg = msgs.find(function(m) { return m.role === 'user'; });
  if (firstUserMsg && !result.user_named) updateSessionTitle(sid, firstUserMsg.text.substring(0, 30));
}

// F3-2: 侧栏该项加载指示开关（呼吸闪烁）
function setSessionLoading(sid, on) {
  var items = sessionListEl.querySelectorAll('.session-item');
  items.forEach(function(d) {
    if (d.dataset.sid === sid) d.classList.toggle('loading', !!on);
  });
}

// TICKET-GUI-F13：考古模式开关 —— F12 历史聚合卡降级为可选"考古模式"（默认关=现场原样）。
// 关（默认）：历史回放与实时同一条渲染链，思考框/工具卡/diff 逐个平铺，展开姿势按持久化还原；
// 开：过往回合"思考→工具×N"链收进聚合卡（F12 行为，F6C .tool-agg 组件复用）。
// 开关持久化 localStorage（bobo_hist_arch_mode），重启保留。
var HIST_ARCH_MODE_KEY = 'bobo_hist_arch_mode';
function histArchMode() {
  try { return localStorage.getItem(HIST_ARCH_MODE_KEY) === '1'; } catch (e) { return false; }
}
function setHistArchMode(on) {
  try { localStorage.setItem(HIST_ARCH_MODE_KEY, on ? '1' : '0'); } catch (e) {}
}

// TICKET-GUI-F13：视觉姿势持久化 —— 每回合最终展开姿势（哪些思考框/工具卡/聚合卡展开）
// 随会话落盘 localStorage（bobo_hist_pose_<sid>），重启回放按姿势还原（现场原样）。
var HIST_POSE_KEY = 'bobo_hist_pose_';
function readPose(sid) {
  try { return JSON.parse(localStorage.getItem(HIST_POSE_KEY + sid) || '{}'); } catch (e) { return {}; }
}
function writePose(sid, pose) {
  try { localStorage.setItem(HIST_POSE_KEY + sid, JSON.stringify(pose)); } catch (e) {}
}
// 扫描当前 chatEl 里所有可展开元素（思考框/工具卡结果/diff/聚合卡）的展开状态，落盘。
function recordPose(sid) {
  var pose = {};
  var els = chatEl.querySelectorAll('.think-box, .tool, .tool-agg');
  els.forEach(function(el) {
    var key = el.dataset && el.dataset.poseId;
    if (!key) return;
    if (el.classList.contains('think-box')) {
      pose[key] = el.classList.contains('collapsed') ? 0 : 1;
    } else if (el.classList.contains('tool-agg')) {
      var body = el.querySelector('.tool-agg-body');
      pose[key] = (body && body.style.display !== 'none') ? 1 : 0;
    } else if (el.classList.contains('tool')) {
      var r = el.querySelector('.tool-result');
      pose[key] = (r && r.classList.contains('open')) ? 1 : 0;
    }
  });
  writePose(sid, pose);
}
// 回放时按持久化姿势还原展开状态（缺失姿势的保持默认折叠，与实时同款）。
function applyPose(sid) {
  var pose = readPose(sid);
  Object.keys(pose).forEach(function(key) {
    var el = chatEl.querySelector('[data-pose-id="' + key + '"]');
    if (!el) return;
    var want = pose[key];
    if (el.classList.contains('think-box')) {
      if (want && el.classList.contains('collapsed')) toggleThinkBox(el);
      else if (!want && !el.classList.contains('collapsed')) toggleThinkBox(el);
    } else if (el.classList.contains('tool-agg')) {
      var body = el.querySelector('.tool-agg-body');
      var open = body && body.style.display !== 'none';
      if (want && !open) { body.style.display = 'block'; var ar = el.querySelector('.tool-agg-arrow'); if (ar) ar.textContent = '▾'; }
      else if (!want && open) { body.style.display = 'none'; var ar2 = el.querySelector('.tool-agg-arrow'); if (ar2) ar2.textContent = '▸'; }
    } else if (el.classList.contains('tool')) {
      var r = el.querySelector('.tool-result');
      var t = el.querySelector('.tool-toggle');
      if (want && r && !r.classList.contains('open')) { r.classList.add('open'); if (t) { t.textContent = '▾'; t.style.display = 'inline'; } }
      else if (!want && r && r.classList.contains('open')) { r.classList.remove('open'); if (t) { t.textContent = '▸'; t.style.display = 'inline'; } }
    }
  });
}

// F3-3: 完整对话渲染 = 归档 archived_messages 全文（按压缩事件顺序）+ 现存消息，
// 每个压缩边界插柔和分隔线。无归档/读失败则现状渲染（现有消息照常展示）。
async function renderFullHistory(sid, result) {
  var msgs = result.messages || [];
  // TICKET-GUI-F6（缺陷 2c）：resume 带回的压缩摘要 → 历史顶部柔和分隔摘要行
  // （复用 addStatus 样式，不动视觉样式；有摘要才渲染，无摘要零变化）
  if (result.summary) {
    addStatus('📋 Earlier summary: ' + result.summary);
  }
  if (window.boboAPI && window.boboAPI.readArchive) {
    try {
      var ar = await window.boboAPI.readArchive(sid);
      if (ar && ar.ok && ar.records && ar.records.length > 0) {
        for (var i = 0; i < ar.records.length; i++) {
          var rec = ar.records[i];
          var ams = rec.archived_messages || [];
          renderArchivedMessages(ams, 'hist-' + sid + '-a' + i + '-');
          var n = rec.pre_msg_count || ams.length;
          addStatus('— ' + n + ' earlier messages compacted —');
        }
      }
    } catch (e) {
      addStatus('⚠ Archive read failed; showing current messages: ' + ((e && e.message) || e));
    }
  }
  // TICKET-GUI-F12：预扫描"最新一轮"起点 —— 最后一条带 tool_calls 的 assistant
  // 消息索引（纯文本回复不是工具链起点）。其后的工具链保持完整平铺
  //（让用户看到"最近一次干了什么"）；更早回合的"思考→工具×N"链收进
  // 聚合卡（考古模式，F6C 组件复用）。
  var histLatestStart = -1;
  for (var hi = msgs.length - 1; hi >= 0; hi--) {
    if (msgs[hi].role === 'assistant' && msgs[hi].tool_calls && msgs[hi].tool_calls.length) {
      histLatestStart = hi; break;
    }
  }
  // TICKET-GUI-F13：考古模式（默认关=现场原样）。关：所有消息平铺（与实时同一条
  // 渲染链）；开：过往回合"思考→工具×N"链收进聚合卡（F12 行为）。
  var archMode = histArchMode();
  // 聚合缓冲：当前链的思考文本 + 收集中的工具消息（仅考古模式启用）
  var aggThink = null;
  var aggTools = [];
  function flushHistAgg() {
    if (aggTools.length === 0) {
      // TICKET-GUI-F12（审查修复）：assistant 声明 tool_calls 但工具消息缺失
      //（归档裁剪/异常）时思考不丢 —— 单独平铺；纯文本链 aggThink 为空零影响
      if (aggThink) addHistThinking(aggThink);
      aggThink = null;
      return;
    }
    renderHistAggCard(aggThink, aggTools);
    aggThink = null;
    aggTools = [];
  }
  var histLatest = false;  // 当前消息是否处于最新一轮（完整平铺）
  msgs.forEach(function(m, idx) {
    if (m.role === 'user') {
      flushHistAgg();
      // TICKET-GUI-F12（审查修复）：user 边界重置 —— 孤儿 tool 消息（归档异常）
      // 跨 user 时不再被误判为最新一轮而平铺
      histLatest = false;
      var uEl = addMsg('user', m.text, 'hist-' + sid + '-u' + idx);
      if (uEl) uEl.setAttribute('data-pose-id', 'u' + idx);
    }
    else if (m.role === 'assistant') {
      flushHistAgg();
      histLatest = (idx === histLatestStart);
      if (m.thinking) {
        // TICKET-GUI-F13：现场原样 —— 思考框一律平铺（默认收起、点击展开，
        // 与实时折叠思考框同交互）；考古模式且非最新一轮才进聚合缓冲
        if (archMode && !histLatest && m.tool_calls && m.tool_calls.length) {
          aggThink = m.thinking;
        } else {
          var tb = buildHistThinkBox(m.thinking);
          tb.setAttribute('data-pose-id', 't' + idx);
          chatEl.appendChild(tb);
        }
      }
      // TICKET-GUI-F6（缺陷 2a）：现存消息里空 assistant（纯工具回合）给占位，
      // 与 renderArchivedMessages 一致，消灭一屏空泡泡
      var aEl = addMsg('bobo', m.text || (m.tool_calls && m.tool_calls.length ? '(tool-call round)' : ''), 'hist-' + sid + '-a' + idx);
      if (aEl) aEl.setAttribute('data-pose-id', 'a' + idx);
    }
    else if (m.role === 'tool') {
      if (archMode && !histLatest) {
        // TICKET-GUI-F12：考古模式过往回合工具收进聚合缓冲（点击考古展开）
        aggTools.push(m);
      } else {
        // TICKET-GUI-F13：现场原样 —— 工具卡平铺（带 diff 保留 F3-5 红绿块，
        // 无 diff 普通工具调用也渲染工具卡，与实时同款 done 态）
        var tc = buildHistToolCard(m.name || 'tool',
          m.inline_diff ? toolSummary({}, m.inline_diff) : String(m.content || '').substring(0, 120));
        tc.setAttribute('data-pose-id', 'c' + idx);
        chatEl.appendChild(tc);
        if (m.inline_diff) {
          var block = document.createElement('div');
          block.innerHTML = diffBlock(m.inline_diff);
          block.firstChild.setAttribute('data-pose-id', 'd' + idx);
          chatEl.appendChild(block.firstChild);
        }
      }
    }
    else if (m.role === 'system' && m.text && m.text.length < 200) {
      flushHistAgg();
      // F2-4: 历史心跳残留（"仍在工作 Ns"）不恢复 —— 避免 owner 截图的多条心跳堆叠复现
      if (m.text.indexOf('仍在工作') === 0) return;
      addStatus(m.text);
    }
  });
  flushHistAgg();
  // TICKET-GUI-F13：回放按持久化姿势还原展开状态（现场原样，缺失姿势保持默认折叠）
  applyPose(sid);
  // TICKET-GUI-F12（审查修复）：scrollTop 统一到末尾滚一次 —— 循环内渲染函数
  // 不再逐条 scroll（长历史避免多次 reflow）
  chatEl.scrollTop = chatEl.scrollHeight;
}

// TICKET-GUI-F13：窗口化惰性渲染（③）—— 长会话 DOM 节点硬上限 + 滚动丝滑。
// 数据与渲染分离：消息先转成 units 数据模型，DOM 只生成视口附近（提前量 ≥2 屏），
// 未渲染区用占位 div（height=持久化实测高度，无实测用估算），滚动条不跳动。
// 阈值以下（≤ HIST_WINDOW_THRESHOLD 条现存消息）走 renderFullHistory 全量路径，
// 既有短会话行为/测试零变化；超阈值才启用窗口化。
var HIST_WINDOW_THRESHOLD = 200;   // 现存消息超过此数启用窗口化
var HIST_PRELOAD_SCREENS = 2;      // 渲染提前量：视口上下各 ≥2 屏
var HIST_MAX_NODES = 600;          // chatEl 直接子节点硬上限（与会话长度无关）
var HIST_HEIGHT_KEY = 'bobo_hist_h_';  // 实测高度持久化（占位高度精确，防滚动跳动）

// 高度缓存：unit 实测 offsetHeight 落盘（bobo_hist_h_<sid> = {idx: h}）
function histUnitH(sid, idx, def) {
  try {
    var m = JSON.parse(localStorage.getItem(HIST_HEIGHT_KEY + sid) || '{}');
    var v = m['u' + idx];
    return (v && v > 0) ? v : def;
  } catch (e) { return def; }
}
function histSaveH(sid, idx, h) {
  if (!h || h <= 0) return;
  try {
    var m = JSON.parse(localStorage.getItem(HIST_HEIGHT_KEY + sid) || '{}');
    m['u' + idx] = h;
    localStorage.setItem(HIST_HEIGHT_KEY + sid, JSON.stringify(m));
  } catch (e) {}
}

// 估算高度（无实测时占位用；实测后以实测为准，滚动条不跳）
function histEstimateH(unit) {
  var k = unit.kind;
  if (k === 'msg') return 26 + Math.ceil((unit.text || '').length / 60) * 22;
  if (k === 'think') return 30 + (unit.text ? Math.min(120, Math.ceil(unit.text.length / 40) * 16) : 0);
  if (k === 'tool') return 34 + (unit.inlineDiff ? Math.min(200, Math.ceil((unit.inlineDiff || '').length / 50) * 16) : 0);
  if (k === 'status') return 24;
  if (k === 'agg') return 40;
  return 30;
}

// 构建 units 数据模型（与 renderFullHistory 同语义：摘要/归档/聚合开关/心跳过滤/占位）
// 返回 units 数组；每 unit 含 kind + 渲染所需字段 + idx（对应消息索引，姿势锚点复用）。
function buildHistUnits(sid, result) {
  var units = [];
  var msgs = result.messages || [];
  if (result.summary) units.push({ kind: 'status', text: '📋 Earlier summary: ' + result.summary, idx: -1 });
  // 归档：整段并入（短段通常已被压缩，不必逐条窗口化；超长归档也走估算占位）
  var ar = result._archiveRecords || null;
  if (ar && ar.length) {
    for (var ai = 0; ai < ar.length; ai++) {
      var ams = ar[ai].archived_messages || [];
      ams.forEach(function(am, aidx) {
        var role = am.role || '';
        var content = (am.content != null && String(am.content)) || '';
        if (role === 'user') units.push({ kind: 'msg', role: 'user', text: content, idx: -1 });
        else if (role === 'assistant') units.push({ kind: 'msg', role: 'bobo', text: content || (am.tool_calls && am.tool_calls.length ? '(tool-call round)' : ''), idx: -1 });
        else if (role === 'tool') units.push({ kind: 'tool', name: am.name || am.tool_name || 'Tool', text: content, idx: -1 });
        else if (role === 'system' && content && content.length < 200) units.push({ kind: 'status', text: content, idx: -1 });
      });
      var n = ar[ai].pre_msg_count || ams.length;
      units.push({ kind: 'status', text: '— ' + n + ' earlier messages compacted —', idx: -1 });
    }
  }
  // 现存消息：与 renderFullHistory 同语义（考古开关 + 最新一轮预扫描 + 姿势锚点）
  var archMode = histArchMode();
  var histLatestStart = -1;
  for (var hi = msgs.length - 1; hi >= 0; hi--) {
    if (msgs[hi].role === 'assistant' && msgs[hi].tool_calls && msgs[hi].tool_calls.length) {
      histLatestStart = hi; break;
    }
  }
  var aggThink = null;
  var aggTools = [];
  function flushAggTo(units) {
    if (aggTools.length === 0) {
      if (aggThink) units.push({ kind: 'think', text: aggThink, idx: -1 });
      aggThink = null;
      return;
    }
    units.push({ kind: 'agg', think: aggThink, tools: aggTools.slice(), idx: -1 });
    aggThink = null;
    aggTools = [];
  }
  var histLatest = false;
  msgs.forEach(function(m, idx) {
    if (m.role === 'user') {
      flushAggTo(units);
      histLatest = false;
      units.push({ kind: 'msg', role: 'user', text: m.text, idx: idx, poseId: 'u' + idx });
    }
    else if (m.role === 'assistant') {
      flushAggTo(units);
      histLatest = (idx === histLatestStart);
      if (m.thinking) {
        if (archMode && !histLatest && m.tool_calls && m.tool_calls.length) {
          aggThink = m.thinking;
        } else {
          units.push({ kind: 'think', text: m.thinking, idx: idx, poseId: 't' + idx });
        }
      }
      units.push({ kind: 'msg', role: 'bobo',
        text: m.text || (m.tool_calls && m.tool_calls.length ? '(tool-call round)' : ''),
        idx: idx, poseId: 'a' + idx });
    }
    else if (m.role === 'tool') {
      if (archMode && !histLatest) {
        aggTools.push(m);
      } else {
        units.push({ kind: 'tool', name: m.name || 'tool', text: String(m.content || '').substring(0, 120),
          inlineDiff: m.inline_diff || '', idx: idx, poseId: 'c' + idx, diffPoseId: 'd' + idx });
      }
    }
    else if (m.role === 'system' && m.text && m.text.length < 200) {
      flushAggTo(units);
      if (m.text.indexOf('仍在工作') === 0) return;
      units.push({ kind: 'status', text: m.text, idx: -1 });
    }
  });
  flushAggTo(units);
  return units;
}

// 单 unit 渲染（与实时同一条渲染链的"历史平铺"形态：思考框/工具卡/diff 复用构造）
function renderHistUnit(unit) {
  var el = null;
  if (unit.kind === 'msg') {
    el = addMsg(unit.role, unit.text, 'hist-' + Math.random());
    if (el && unit.poseId) el.setAttribute('data-pose-id', unit.poseId);
  } else if (unit.kind === 'think') {
    el = buildHistThinkBox(unit.text);
    if (unit.poseId) el.setAttribute('data-pose-id', unit.poseId);
    chatEl.appendChild(el);
  } else if (unit.kind === 'tool') {
    el = buildHistToolCard(unit.name, unit.inlineDiff ? toolSummary({}, unit.inlineDiff) : unit.text);
    if (unit.poseId) el.setAttribute('data-pose-id', unit.poseId);
    chatEl.appendChild(el);
    if (unit.inlineDiff) {
      var block = document.createElement('div');
      block.innerHTML = diffBlock(unit.inlineDiff);
      var diffEl = block.firstChild;
      if (unit.diffPoseId) diffEl.setAttribute('data-pose-id', unit.diffPoseId);
      chatEl.appendChild(diffEl);
    }
  } else if (unit.kind === 'status') {
    addStatus(unit.text);
  } else if (unit.kind === 'agg') {
    var agg = document.createElement('div'); agg.className = 'tool-agg hist-agg';
    agg.setAttribute('data-pose-id', 'agg' + (histAggSeq++));
    var headLabel = (unit.think ? 'Think + ' : '') + unit.tools.length + ' tools';
    agg.innerHTML = '<span class="tool-agg-head">' + headLabel + ' <span class="tool-agg-arrow">▸</span></span><div class="tool-agg-body" style="display:none"></div>';
    agg.onclick = function(e) {
      if (e.target.closest('.tool') || e.target.closest('.think-box') || e.target.closest('.diff-block')) return;
      var body = this.querySelector('.tool-agg-body');
      if (!body) return;  // 票 SAFETY-1：DOM 结构异常时跳过，防 textContent 空引用
      var open = body.style.display !== 'none';
      body.style.display = open ? 'none' : 'block';
      var arrowEl = this.querySelector('.tool-agg-arrow');
      if (arrowEl) arrowEl.textContent = open ? '▸' : '▾';  // 票 SAFETY-1：空值守卫
    };
    var aggBody = agg.querySelector('.tool-agg-body');
    if (unit.think) aggBody.appendChild(buildHistThinkBox(unit.think));
    unit.tools.forEach(function(tm) {
      var inlineDiff = tm.inline_diff || '';
      aggBody.appendChild(buildHistToolCard(tm.name || 'tool', inlineDiff ? toolSummary({}, inlineDiff) : String(tm.content || '').substring(0, 120)));
      if (inlineDiff) {
        var b2 = document.createElement('div');
        b2.innerHTML = diffBlock(inlineDiff);
        aggBody.appendChild(b2.firstChild);
      }
    });
    chatEl.appendChild(agg);
  }
  return el;
}

// 窗口化渲染：视口 ±2 屏内真实 DOM，其余占位 div（高度=实测/估算）
var histWindowUnits = null;  // 当前窗口化会话的 units（滚动监听引用）
var histWindowSid = null;
function renderHistWindow() {
  if (!histWindowUnits) return;
  var viewH = chatEl.clientHeight || 600;
  var top = chatEl.scrollTop;
  var preload = HIST_PRELOAD_SCREENS * viewH;
  var winTop = Math.max(0, top - preload);
  var winBottom = top + viewH + preload;
  // 累积高度定位窗口覆盖的 unit 区间
  var heights = histWindowUnits.map(function(u) {
    return histUnitH(histWindowSid, u.idx, histEstimateH(u));
  });
  var cum = [0];
  for (var i = 0; i < heights.length; i++) cum.push(cum[i] + heights[i]);
  var total = cum[cum.length - 1];
  if (total <= 0) total = viewH;
  // 二分定位 startIdx（cum[startIdx] >= winTop 的最小下标）
  function lowerBound(arr, val) {
    var lo = 0, hi = arr.length - 1;
    while (lo < hi) {
      var mid = (lo + hi) >> 1;
      if (arr[mid] < val) lo = mid + 1; else hi = mid;
    }
    return lo;
  }
  var startIdx = Math.max(0, lowerBound(cum, winTop) - 1);
  var endIdx = Math.min(histWindowUnits.length - 1, lowerBound(cum, winBottom) + 1);
  // 重建 chatEl：顶部占位 + 窗口内真实 unit + 底部占位
  var topH = cum[startIdx];
  var bottomH = total - cum[endIdx + 1];
  chatEl.innerHTML = '';
  if (topH > 0) {
    var tp = document.createElement('div'); tp.className = 'hist-ph'; tp.style.height = topH + 'px';
    chatEl.appendChild(tp);
  }
  for (var ui = startIdx; ui <= endIdx; ui++) {
    var u = histWindowUnits[ui];
    var before = chatEl.childNodes.length;
    renderHistUnit(u);
    // 实测高度落盘（精确占位，下次滚动不跳）
    var rendered = chatEl.childNodes;
    for (var ci = before; ci < rendered.length; ci++) {
      if (rendered[ci] && rendered[ci].offsetHeight && u.idx >= 0) {
        histSaveH(histWindowSid, u.idx, rendered[ci].offsetHeight);
      }
    }
  }
  if (bottomH > 0) {
    var bp = document.createElement('div'); bp.className = 'hist-ph'; bp.style.height = bottomH + 'px';
    chatEl.appendChild(bp);
  }
  // 姿势还原（窗口内元素）
  applyPose(histWindowSid);
  // 节点数硬上限：占位 2 + 窗口内单元节点（每个 unit 摊 2-4 节点）恒 ≤ HIST_MAX_NODES
}

// 窗口化滚动监听（rAF 节流，滚动丝滑不卡顿）
var histWindowRAF = null;
function histWindowOnScroll() {
  // TICKET-GUI-F19：回合进行中（思考/工具/回复流式，currentBusy=true）不重建。
  // 用 currentBusy() 而非 thinkBoxEl：工具执行阶段 thinkBoxEl 已被 tool.start 收束置 null，
  // 但回合仍在跑（tool 卡/diff 实时更新中）——此时重建会清掉实时节点。
  // currentBusy 覆盖整个回合（message.start 置 busy → complete/中断清 busy）。
  if (currentBusy()) return;
  if (histWindowRAF) return;
  histWindowRAF = requestAnimationFrame(function() {
    histWindowRAF = null;
    if (histWindowUnits) renderHistWindow();
  });
}

// 窗口化入口：长会话启用（数据/渲染分离），短会话走 renderFullHistory（零变化）
async function renderFullHistoryWindowed(sid, result) {
  // 归档记录经 boboAPI 预取（与 renderFullHistory 同路径；失败静默）
  var ar = null;
  if (window.boboAPI && window.boboAPI.readArchive) {
    try {
      var r = await window.boboAPI.readArchive(sid);
      if (r && r.ok && r.records && r.records.length) ar = r.records;
    } catch (e) { ar = null; }
  }
  result._archiveRecords = ar;
  var units = buildHistUnits(sid, result);
  histWindowUnits = units;
  histWindowSid = sid;
  renderHistWindow();
  // 滚动监听（只绑一次，rAF 节流）
  if (!chatEl._histWindowBound) {
    chatEl.addEventListener('scroll', histWindowOnScroll);
    chatEl._histWindowBound = true;
  }
}

// F3-3: 渲染归档消息（role: user/assistant/system/tool；assistant 纯工具回合给占位）
function renderArchivedMessages(ams, idPrefix) {
  ams.forEach(function(m, idx) {
    var role = m.role || '';
    var content = (m.content != null && String(m.content)) || '';
    var id = idPrefix + idx;
    if (role === 'user') addMsg('user', content, id);
    else if (role === 'assistant') addMsg('bobo', content || (m.tool_calls && m.tool_calls.length ? '(tool-call round)' : ''), id);
    else if (role === 'tool') addTool(m.name || m.tool_name || 'Tool', content, id + '-t');
    else if (role === 'system' && content && content.length < 200) addStatus(content);
  });
}

// TICKET-GUI-F12（审查修复）：历史思考折叠框构造 —— 复用 think-box.collapsed 样式
//（默认收起、点击 ▸ 展开/收起，与实时折叠思考框同交互）；返回 DOM 由调用方 append。
// addHistThinking / renderHistAggCard 共用，消除双份维护
function buildHistThinkBox(thinkingText) {
  var tb = document.createElement('div');
  tb.className = 'think-box collapsed';
  tb.innerHTML = '<div class="think-label"><span>thinking</span><span class="tool-toggle">▸</span></div><div class="think-text"></div>';
  var txt = tb.querySelector('.think-text');
  if (txt) txt.textContent = thinkingText || '';
  tb.onclick = function(e) {
    // 点内容文本时允许选择，不触发折叠切换（与实时折叠框一致）
    if (e && e.target && e.target.closest && e.target.closest('.think-text')) return;
    toggleThinkBox(tb);
  };
  return tb;
}

// TICKET-GUI-F12（审查修复）：历史工具卡构造 —— 一行摘要（done 态），返回 DOM
// 由调用方 append。renderHistToolDiff / renderHistToolFlat / renderHistAggCard 共用
function buildHistToolCard(name, summary) {
  var friendly = TOOL_FRIENDLY[name] || name;
  var card = document.createElement('div'); card.className = 'tool';
  card.setAttribute('data-tool', name);
  // TICKET-DESK-V2D25：历史卡带细线图标 + 完成态实心点（灰绿）；历史是静的，不带流光
  card.setAttribute('data-state', 'done');
  card.innerHTML = toolIcon(name) +
    '<span class="dot done"></span>' +
    '<span class="tool-name">' + esc(friendly) + '</span>' +
    '<div class="tool-result"><div class="tool-summary">' + esc(summary) + '</div></div>';
  return card;
}

// TICKET-GUI-F8：历史折叠思考框 —— 复用 think-box.collapsed 样式（默认收起，
// 点击 ▸ 展开/收起，与实时折叠思考框同交互）；渲染在对应 assistant 消息上方
function addHistThinking(thinkingText) {
  chatEl.appendChild(buildHistThinkBox(thinkingText));
}

// TICKET-GUI-F8：历史工具 diff —— 工具卡一行摘要（done 态）+ F3-5 同款整行底色
// 红绿块（diffBlock），独立出现在消息流对应位置，默认展开与实时一致
//（TICKET-GUI-F12 审查修复：工具卡构造复用 buildHistToolCard；scrollTop 交由
// renderFullHistory 末尾统一滚动）
function renderHistToolDiff(name, inlineDiff) {
  chatEl.appendChild(buildHistToolCard(name, toolSummary({}, inlineDiff)));
  var block = document.createElement('div');
  block.innerHTML = diffBlock(inlineDiff);
  chatEl.appendChild(block.firstChild);
}

// TICKET-GUI-F12：最新一轮无 diff 工具卡平铺 —— 历史不再丢普通工具调用
//（工具卡一行摘要 + done 态；无 inline_diff 不产红绿块，语义零新增）
function renderHistToolFlat(name, content) {
  chatEl.appendChild(buildHistToolCard(name, String(content).substring(0, 120)));
}

// TICKET-GUI-F12：历史聚合卡 —— 过往回合"思考→工具×N"链收进考古卡（复用 F6C
// .tool-agg 组件：头点击展开/收起，body 内思考框（think-box collapsed）+ 逐个工具卡，
// 带 inline_diff 的附 F3-5 整行红绿 diff 块，红绿语义与实时一致；零新增颜色）
//（审查修复：onclick guard 补 .think-box/.diff-block —— 点思考框展开时事件冒泡到
// 聚合卡头会误收整卡；构造复用 buildHistThinkBox/buildHistToolCard；scrollTop 交由
// renderFullHistory 末尾统一滚动）
// TICKET-GUI-F13：聚合卡打 data-pose-id（bobo_hist_pose_<sid> 姿势还原锚点）
var histAggSeq = 0;
function renderHistAggCard(thinkText, toolMsgs) {
  var agg = document.createElement('div'); agg.className = 'tool-agg hist-agg';
  agg.setAttribute('data-pose-id', 'agg' + (histAggSeq++));
  var headLabel = (thinkText ? 'Think + ' : '') + toolMsgs.length + ' tools';
  agg.innerHTML = '<span class="tool-agg-head">' + headLabel + ' <span class="tool-agg-arrow">▸</span></span><div class="tool-agg-body" style="display:none"></div>';
  agg.onclick = function(e) {
    if (e.target.closest('.tool') || e.target.closest('.think-box') || e.target.closest('.diff-block')) return;
    var body = this.querySelector('.tool-agg-body');
    if (!body) return;  // 票 SAFETY-1：DOM 结构异常时跳过，防 textContent 空引用
    var open = body.style.display !== 'none';
    body.style.display = open ? 'none' : 'block';
    var arrowEl = this.querySelector('.tool-agg-arrow');
    if (arrowEl) arrowEl.textContent = open ? '▸' : '▾';  // 票 SAFETY-1：空值守卫
  };
  var aggBody = agg.querySelector('.tool-agg-body');
  // 思考框进考古卡（同 addHistThinking：默认收起、点击展开）
  if (thinkText) aggBody.appendChild(buildHistThinkBox(thinkText));
  toolMsgs.forEach(function(m) {
    var name = m.name || 'tool';
    var inlineDiff = m.inline_diff || '';
    aggBody.appendChild(buildHistToolCard(name, inlineDiff ? toolSummary({}, inlineDiff) : String(m.content || '').substring(0, 120)));
    // F3-5 红绿块语义不变：diff 同级独立块，整行底色
    if (inlineDiff) {
      var block = document.createElement('div');
      block.innerHTML = diffBlock(inlineDiff);
      aggBody.appendChild(block.firstChild);
    }
  });
  chatEl.appendChild(agg);
}

async function newChat() {
  var result = await call('session.create', { title: 'New Chat' });
  if (result && result.session_id) {
    currentSessionId = result.session_id;
    clearChat();
    showInputBox();  // 恢复输入框（onNavNewSession 先 hideAllViews 隐藏了它）
    sessions.unshift({ id: result.session_id, title: 'New Chat' });
    renderSessions();
    renderBusyUI();   // V4B⓪：新会话即空闲态（不继承旧会话忙碌）
    // TICKET-DESK-V4B：新会话即当前会话，广播给小窗（跟随模式基准）
    if (typeof window !== 'undefined' && window.boboAPI && window.boboAPI.widgetCurrentSession) {
      window.boboAPI.widgetCurrentSession(result.session_id, 'New Chat');
    }
    // F2-2: 新会话默认非 AUTO（后端 auto_mode 新会话默认 False）
    setMode('');
    call('session.activate', { session_id: result.session_id });
  }
}

// ── Connect & events ───────────────────────────────────────────────────
connect();

on('gateway.ready', async function() {
  debug('Connected, restoring sessions...');
  // TICKET-DESK-V2A：曾处于覆盖层态（连接中/失败/断连）时，恢复后 toast 告知
  var wasCovered = _ovlType !== null;
  _everConnected = true;
  setConnected(true);
  hideOverlay();
  if (wasCovered) showToast('success', 'Connection restored');
  await loadSessions();
  // ── TICKET-GUI-F14：解耦——无依赖初始化先行，loadSession 卡死/失败不再拖死整链 ──
  renderPluginList();
  document.getElementById('body-plugin').classList.add('closed');
  document.getElementById('arr-plugin').classList.add('closed');
  refreshCtxStats();   // TICKET-DESK-V2B：就绪后初始刷新上下文仪表盘
  loadSlashCatalog();  // TICKET-DESK-V2B3：就绪后拉取命令目录（命令面板数据源）
  // ── TICKET-GUI-F14：会话加载兜底——15s 超时 + 失败 toast + 空态可发新消息，绝不静默 ──
  var LOAD_TIMEOUT_MS = 15000;
  function withTimeout(p, label) {
    return Promise.race([p, new Promise(function(_, rej) {
      setTimeout(function() { rej(new Error(label + ' timed out (15s)')); }, LOAD_TIMEOUT_MS);
    })]);
  }
  if (sessions.length > 0) {
    currentSessionId = sessions[0].id;
    try {
      await withTimeout(loadSession(sessions[0].id), 'Load session');
    } catch (e) {
      var em = (e && e.message) || 'Unknown error';
      showToast('fail', 'Failed to load session: ' + em + ' — you can still send a message');
      addStatus('⚠ Failed to load session: ' + em + ' (ready for a new message)');
      clearChat();   // 欢迎空态：仍可发新消息
    }
    renderSessions();
  } else {
    // GUI-F14 同链路自查：newChat 分支同样不阻塞后续初始化（超时视同失败，绝不停链）
    try {
      await withTimeout(newChat(), 'New chat');
    } catch (e) {
      showToast('fail', 'Failed to create chat: ' + ((e && e.message) || 'Unknown error') + ' — you can still send a message');
    }
  }
  debug('Ready'); inputEl.focus();
});

var streamingId = null;
var thinkText = '';
// TICKET-GUI-F19b：推理过程独立缓冲（reasoning.delta 流）——与正文 thinkText 分离，
// 推理实时滚动显示在思考框；正文到达后思考框转显正文，推理内容 complete 时收进折叠框。
var reasoningText = '';
var toolsCalledThisRound = false;
var thinkBoxEl = null;
// TICKET-DESK-V2D5：认知状态条 —— 本轮记忆注入条数（memory_injected 回合内增量）+ 本轮工具调用数（tool.start 计数）
var roundMemBaseline = null;
var roundMemInjected = 0;
var roundToolCount = 0;

function createThinkBox() {
  var tb = document.createElement('div');
  tb.className = 'think-box show';
  tb.innerHTML = '<div class="think-label"><span>Thinking</span><span class="think-dot"></span><span class="think-dot"></span><span class="think-dot"></span><span class="think-stop" title="Stop" onclick="stopThinking()">✕</span></div><div class="think-text"></div>';
  chatEl.appendChild(tb);
  chatEl.scrollTop = chatEl.scrollHeight;
  // 10s: show warning
  tb._warnTimer = setTimeout(function() {
    if (tb.parentNode) {
      tb.querySelector('.think-label').innerHTML += ' <span style="color:#f48771;font-weight:400;font-size:10px;">(slow response...)</span>';
    }
  }, 10000);
  // 30s: auto-timeout — API likely hung
  tb._killTimer = setTimeout(function() {
    if (tb.parentNode) {
      tb.querySelector('.think-text').textContent = 'API unresponsive. Retry later or click ✕ to stop.';
      tb.querySelector('.think-label').innerHTML = '<span style="color:#f48771">⚠ Timeout</span>';
    }
  }, 30000);
  return tb;
}

// TICKET-GUI-F1 (F1-2): 从 final_text 剥离思考段（── 💭 思考过程 ── ... [── 思考结束 ──]）
// 返回 { body: 正文, thinking: 思考内容 }。无思考段则 body=全文、thinking=''。
function splitThinking(s) {
  if (!s) return { body: '', thinking: '' };
  var m = s.match(/(?:^|\n)──\s*💭\s*思考过程\s*──\n([\s\S]*?)(?:──\s*思考结束\s*(?:──)?[^\n]*\n?)?$/);
  if (m) {
    return { body: s.slice(0, m.index).trim(), thinking: m[1].trim() };
  }
  return { body: s.trim(), thinking: '' };
}
// F1-2: 流式 thinking 框 → 折叠摘要框（清 timer/动画，label 变摘要行，内容保留）
function collapseThinkBox(tb, thinkingText) {
  if (!tb) return;
  if (tb._warnTimer) clearTimeout(tb._warnTimer);
  if (tb._killTimer) clearTimeout(tb._killTimer);
  tb._warnTimer = null; tb._killTimer = null;
  var dots = tb.querySelectorAll('.think-dot');
  for (var i = 0; i < dots.length; i++) dots[i].remove();
  var stopBtn = tb.querySelector('.think-stop');
  if (stopBtn) stopBtn.remove();
  var label = tb.querySelector('.think-label');
  if (label) label.innerHTML = '<span>thinking</span><span class="tool-toggle">▸</span>';
  var txt = tb.querySelector('.think-text');
  if (txt) txt.textContent = thinkingText || '';
  tb.classList.remove('show');
  tb.classList.add('collapsed');
  tb.onclick = function(e) {
    // 点内容文本时允许选择，不触发折叠切换
    if (e && e.target && e.target.closest && e.target.closest('.think-text')) return;
    toggleThinkBox(tb);
  };
}
// F1-2: 折叠/展开切换（▸/▾）
function toggleThinkBox(tb) {
  if (!tb) return;
  var nowShow = tb.classList.toggle('show');
  tb.classList.toggle('collapsed', !nowShow);
  var toggle = tb.querySelector('.tool-toggle');
  if (toggle) toggle.textContent = nowShow ? '▾' : '▸';
}
function stopThinking() {
  showStop(false);   // TICKET-D1d ⑤
  setSidBusy(currentSessionId, false); renderBusyUI();   // V4B⓪：中断后立即恢复当前会话空闲态
  reasoningText = '';   // TICKET-GUI-F19b：中断即弃推理缓冲，防残留进下回合
  if (thinkBoxEl) {
    if (thinkBoxEl._warnTimer) clearTimeout(thinkBoxEl._warnTimer);
    if (thinkBoxEl._killTimer) clearTimeout(thinkBoxEl._killTimer);
    if (currentSessionId) call('session.interrupt', { session_id: currentSessionId });
    thinkBoxEl.remove(); thinkBoxEl = null;
  }
  addStatus('Stopped');
}

// ── Worker 折叠卡（TICKET-DESK-WORKER-VISIBLE）──
// spawn_worker 主卡标题直接写角色名（explorer/coder）；worker 内部活动
// （工具调用/单步收工/阶段思考）渲染进该 worker 独立的折叠卡，运行时可展开看；
// worker 收工（spawn_worker 的 tool.complete）后收纳进主卡 .worker-slot，点击主卡展开考古。
// 配对键 = 后端 resolve_worker_card_meta 的 worker 字段（与 Worker 回调标识一致）。
var workerMainCards = {};   // worker 键 → 主卡 div
var workerCards = {};       // worker 键 → 独立折叠卡 div
// worker 内部事件判别：带 worker 标识且不是 spawn_worker 主卡本身
function isWorkerEvent(d) { return !!(d && d.worker && d.name !== 'spawn_worker'); }
// 主卡挂收纳位（.worker-slot），并登记配对
function setupWorkerMainCard(card, key) {
  if (!card || !key) return;
  card.setAttribute('data-worker', key);
  var slot = document.createElement('div');
  slot.className = 'worker-slot';
  card.appendChild(slot);
  workerMainCards[key] = card;
}
// 取/建 worker 独立折叠卡（默认展开，头部点击折叠）
function ensureWorkerCard(key, role) {
  if (workerCards[key]) return workerCards[key];
  var card = document.createElement('div');
  card.className = 'worker-card';
  card.setAttribute('data-worker', key);
  var head = document.createElement('div');
  head.className = 'worker-head';
  head.innerHTML = '<span class="worker-role">' + esc(role || 'Worker') + '</span>' +
    (key && key !== 'worker' ? '<span class="worker-name">' + esc(key) + '</span>' : '') +
    '<span class="worker-phase"></span>' +
    '<span class="worker-toggle">▾</span>';
  var body = document.createElement('div');
  body.className = 'worker-body';
  card.appendChild(head);
  card.appendChild(body);
  card.onclick = function(e) {
    if (e.target.closest('.worker-body')) return;   // 行内点选/滚动不折叠
    var open = body.style.display !== 'none';
    body.style.display = open ? 'none' : 'block';
    var tg = head.querySelector('.worker-toggle');
    if (tg) tg.textContent = open ? '▾' : '▸';
  };
  chatEl.appendChild(card);
  chatEl.scrollTop = chatEl.scrollHeight;
  workerCards[key] = card;
  return card;
}
// worker 工具调用行
function renderWorkerToolStart(data) {
  var card = ensureWorkerCard(data.worker, data.role);
  var body = card.querySelector('.worker-body');
  var row = document.createElement('div');
  row.className = 'worker-row';
  row.setAttribute('data-wrow', data.tool_id || '');
  row.innerHTML = toolIcon(data.name) +
    '<span class="worker-row-name">' + esc(TOOL_FRIENDLY[data.name] || data.name) + '</span>' +
    (data.context ? '<span class="worker-row-preview">' + esc(data.context) + '</span>' : '') +
    '<span class="worker-row-time"></span>' +
    '<span class="dot ring"></span>';
  body.appendChild(row);
  chatEl.scrollTop = chatEl.scrollHeight;
}
// worker 单步收工：行内 dot 转 done/fail + 耗时
function renderWorkerToolComplete(data) {
  var card = workerCards[data.worker];
  if (!card) return;
  var rows = card.querySelectorAll('.worker-row[data-wrow="' + data.tool_id + '"]');
  if (!rows.length) return;
  var row = rows[rows.length - 1];
  var dot = row.querySelector('.dot');
  if (dot) dot.className = 'dot ' + (data.success === false ? 'fail' : 'done');
  var dur = Number(data.duration || 0);
  var tm = row.querySelector('.worker-row-time');
  if (tm && dur > 0) tm.textContent = dur.toFixed(1) + 's';
}
// worker 阶段/思考：头部实时阶段提示（正在思考…/并行执行 N 个工具/工具执行完成）
function renderWorkerPhase(data) {
  var card = ensureWorkerCard(data.worker, data.role);
  var ph = card.querySelector('.worker-phase');
  var msg = data.message || '';
  if (ph && msg) ph.textContent = '· ' + msg.slice(0, 30);
}
// worker 收工 → 独立折叠卡收纳进主卡 .worker-slot（默认折叠，点击主卡展开）
function foldWorkerIntoMain(key) {
  var main = workerMainCards[key];
  var wc = workerCards[key];
  workerMainCards[key] = null;
  workerCards[key] = null;
  if (!main || !wc) return;
  var slot = main.querySelector('.worker-slot');
  if (slot) {
    slot.appendChild(wc);
    slot.classList.remove('open');
  }
  chatEl.scrollTop = chatEl.scrollHeight;
}

on('message.start', function(data) {
  if (isForeignSession(data)) return;
  if (sendTimeoutId) { clearTimeout(sendTimeoutId); sendTimeoutId = null; }
  setSidBusy(data ? data.session_id : '', true);   // V4B⓪：忙碌按会话登记
  renderBusyUI(); debug('Receiving...');           // V4B⓪：UI 按当前显示会话刷新
  thinkText = '';
  toolsCalledThisRound = false;
  streamingId = null;
  reasoningText = '';   // TICKET-GUI-F19b：新回合重置推理缓冲
  welcomeEl.style.display = 'none';
  thinkBoxEl = createThinkBox();
});

on('message.delta', function(data) {
  if (isForeignSession(data)) return;
  var t = data ? data.text || '' : '';
  if (t) {
    // TICKET-GUI-F6（缺陷 1）：思考分段 —— 当前无打开思考框（已被 tool.start
    // 收束为折叠段）时另开新框，让后续思考独立成段，与工具卡交错排列
    // TICKET-GUI-F6B（F6 精化）：连续思考合并 —— 分段只发生在工具边界。
    // 无打开框时先看消息流末尾紧邻元素：若是已收束的折叠思考框（中间无工具卡/
    // 正文/diff），把新思考追加进该框（换行衔接），不另开新框；隔了工具卡/正文
    // 则照常新建（F6 行为保留）
    if (!thinkBoxEl) {
      var lastEl = chatEl.lastElementChild;
      // TICKET-GUI-F6D：相邻判定跳过状态行（status 类非结构节点）——状态行插在
      // 思考框之间不再打断合并判定（owner 实证：状态行致思考框连排成墙）
      while (lastEl && lastEl.classList && lastEl.classList.contains('status')) {
        lastEl = lastEl.previousElementSibling;
      }
      if (lastEl && lastEl.classList && lastEl.classList.contains('think-box') &&
          lastEl.classList.contains('collapsed')) {
        thinkBoxEl = lastEl;
        var prevTxt = thinkBoxEl.querySelector('.think-text');
        thinkText = (prevTxt && prevTxt.textContent) ? prevTxt.textContent + '\n' : '';
      } else {
        thinkBoxEl = createThinkBox();
      }
    }
    thinkText += t;
    // TICKET-GUI-F27：thinking 流式活动刷新——收到内容重置 10s/30s 计时器
    //（推理模型思考可 >30s，固定 30s 硬超时必然误报 "API unresponsive"；
    // 只有 30s 完全无流（真挂起）才提示超时）
    if (thinkBoxEl) {
      if (thinkBoxEl._warnTimer) { clearTimeout(thinkBoxEl._warnTimer); thinkBoxEl._warnTimer = null; }
      if (thinkBoxEl._killTimer) {
        clearTimeout(thinkBoxEl._killTimer);
        thinkBoxEl._killTimer = setTimeout(function() {
          if (thinkBoxEl && thinkBoxEl.parentNode) {
            thinkBoxEl.querySelector('.think-text').textContent = 'API unresponsive. Retry later or click ✕ to stop.';
            thinkBoxEl.querySelector('.think-label').innerHTML = '<span style="color:#f48771">⚠ Timeout</span>';
          }
        }, 30000);
      }
    }
    var txt = thinkBoxEl.querySelector('.think-text');
    if (txt) {
      txt.textContent = thinkText;
      // TICKET-GUI-F19：滚动锚定 —— 用户上翻历史时不被流式强制拉回底部。
      // 死循环根因（RWORK-F29 项6）：无条件 scrollTop=scrollHeight 触发 scroll 事件
      // → 窗口化重建（renderHistWindow innerHTML=''）→ 清掉实时 thinking 框 → 卡屏。
      // 仅当用户已在底部附近（<80px）才跟随滚动；上翻时不动 scrollTop，不触发重建。
      var nearBottom = chatEl.scrollHeight - chatEl.scrollTop - chatEl.clientHeight < 80;
      if (nearBottom) chatEl.scrollTop = chatEl.scrollHeight;
    }
  }
});
// TICKET-GUI-F19b：推理过程实时流（reasoning.delta）——模型思考期间思考框实时滚动。
// 之前桌面端漏监听此事件：模型思考 10-40 秒（deepseek thinking 模式）期间思考框空白，
// 用户感知"回复变慢"。TUI 端（entry.js recordReasoningDelta）早有此通道，桌面端补齐。
on('reasoning.delta', function(data) {
  if (isForeignSession(data)) return;
  var t = data ? data.text || '' : '';
  if (!t) return;
  if (!thinkBoxEl) thinkBoxEl = createThinkBox();
  reasoningText += t;
  var txt = thinkBoxEl.querySelector('.think-text');
  if (txt) {
    txt.textContent = reasoningText;
    // TICKET-GUI-F19：与 message.delta 同款滚动锚定（仅底部附近跟随）
    var nearBottom = chatEl.scrollHeight - chatEl.scrollTop - chatEl.clientHeight < 80;
    if (nearBottom) chatEl.scrollTop = chatEl.scrollHeight;
  }
});
on('message.complete', function(data) {
  if (isForeignSession(data)) return;
  setSidBusy(data ? data.session_id : '', false);   // V4B⓪：清该会话忙碌位
  renderBusyUI(); debug('Connected ✓');             // V4B⓪：UI 按当前显示会话刷新
  var toolsWereCalled = toolIdCounter > 0;
  thinkText = '';
  if (streamingId) { var old = document.getElementById(streamingId); if (old) old.remove(); streamingId = null; }
  toolIdCounter = 0;
  // F2-3: 回合结束重置聚合状态（下回合重新计数）
  roundToolEls = []; roundAggregated = false; roundTotalCount = 0; roundAggregateHead = null;
  var t = data ? data.final_text || '' : '';
  // TICKET-GUI-F1 (F1-2): 剥离思考段（── 💭 思考过程 ── ...）收进蓝色框默认折叠，正文零泄漏
  var split = splitThinking(t);
  var body = split.body;
  var thinking = split.thinking;
  // TICKET-GUI-F19b：推理过程独立流（reasoning.delta）——若本轮有推理内容且 final_text
  // 未含思考段（DeepSeek thinking 模式推理走独立通道），用它作为折叠框内容；否则用剥离段。
  if (!thinking && reasoningText.trim()) {
    thinking = reasoningText.trim();
  }
  reasoningText = '';   // 消费即清，防串回合
  if (body && body.trim()) {
    if (thinking) {
      // TICKET-GUI-F6（缺陷 1）：思考分段后 thinkBoxEl 可能已被 tool.start 置空，
      // 此时 final 思考另开新框收束，保证思考段不丢
      if (!thinkBoxEl) thinkBoxEl = createThinkBox();
      collapseThinkBox(thinkBoxEl, thinking);
    } else if (thinkBoxEl) {
      thinkBoxEl.remove(); thinkBoxEl = null;
    }
    addMsg('bobo', body, 'msg-' + Date.now());
  } else if (thinking) {
    // 纯工具回合：只有思考无正文 → 保留折叠框（thinkBoxEl 可能为空，另开新框收束）
    if (!thinkBoxEl) thinkBoxEl = createThinkBox();
    collapseThinkBox(thinkBoxEl, thinking);
  } else if (toolsWereCalled && thinkBoxEl) {
    // All tool calls done with no final text — clean up think box
    if (thinkBoxEl._warnTimer) clearTimeout(thinkBoxEl._warnTimer);
    if (thinkBoxEl._killTimer) clearTimeout(thinkBoxEl._killTimer);
    thinkBoxEl.remove(); thinkBoxEl = null;
  } else if (thinkBoxEl) {
    if (thinkBoxEl._warnTimer) clearTimeout(thinkBoxEl._warnTimer);
    if (thinkBoxEl._killTimer) clearTimeout(thinkBoxEl._killTimer);
    thinkBoxEl.style.opacity = '0.5';
  }
  loadSessions();
  refreshCtxStats();   // TICKET-DESK-V2B：回合结束刷新上下文仪表盘
  // TICKET-GUI-F19：回合结束立即校准窗口化坐标系（用实测高度重建一次）。
  // 把"跳"从"用户下次滚动时"提前到"回合刚结束瞬间"——用户注意力在回复内容上，
  // 感知最弱；此后滚动时坐标系已准，无位置错位。
  if (histWindowUnits) renderHistWindow();
  // TICKET-GUI-F13：回合结束把最终展开姿势落盘（重启回放按姿势还原现场原样）
  if (currentSessionId) recordPose(currentSessionId);
});
// TICKET-DESK-WORKER-VISIBLE：worker 阶段/思考 → 独立折叠卡头部实时阶段
// （主引擎 thinking 由 engine_adapter 转 status.update 走原通道，这里只处理带 worker
// 标识的事件，非 worker 的 thinking 维持现状不渲染，不改变现有行为）
on('thinking', function(data) {
  if (isForeignSession(data)) return;
  if (isWorkerEvent(data)) renderWorkerPhase(data);
});
on('tool.start', function(data) {
  if (isForeignSession(data)) return;
  // TICKET-DESK-WORKER-VISIBLE：worker 内部事件 → 独立折叠卡（不进普通工具卡/聚合卡）
  if (isWorkerEvent(data)) { renderWorkerToolStart(data); return; }
  // TICKET-DESK-WORKER-VISIBLE：spawn_worker 主卡 —— 标题直接写角色名，预留收纳位
  var isSpawn = !!(data && data.name === 'spawn_worker');
  // TICKET-GUI-F6（缺陷 1）：工具卡是天然分段点 —— 到达时把当前思考框收束为
  // 折叠摘要段（复用 collapseThinkBox，视觉样式不动），后续 thinking.delta
  // 另开新框，思考段与工具卡交错排列，对齐 TUI/Hermes 节奏
  if (thinkBoxEl) {
    collapseThinkBox(thinkBoxEl, thinkText);
    thinkBoxEl = null;
    thinkText = '';
    // TICKET-GUI-F19b（回归修复）：工具边界同时清推理缓冲——此前漏清导致
    // 下一次思考在旧推理上追加（"叠罗汉"越滚越长，回合结束才整体收进折叠框）
    reasoningText = '';
  }
  toolsCalledThisRound = true;
  // TICKET-DESK-V2D5：本轮工具调用计数（认知状态条数据源）
  roundToolCount++;
  var card = addTool(data ? data.name || data.tool_id || 'Tool' : 'Tool',
                     isSpawn ? (data.worker || data.context || '') : (data ? data.context || '' : ''),
                     data ? data.tool_id || 't'+Date.now() : 't'+Date.now(),
                     isSpawn ? (data.worker_role || data.worker || '') : '');
  if (isSpawn && data.worker) setupWorkerMainCard(card, data.worker);
});
on('tool.complete', function(data) {
  if (isForeignSession(data)) return;
  // TICKET-DESK-WORKER-VISIBLE：worker 内部事件 → 折叠卡内单步收工（dot 转 done/fail）
  if (isWorkerEvent(data)) { renderWorkerToolComplete(data); return; }
  var tid = data ? data.tool_id || '' : '';
  if (tid) updateToolResult(tid, data);
  // TICKET-DESK-WORKER-VISIBLE：spawn_worker 收工 → 把该 worker 的折叠卡收纳进主卡
  if (data && data.name === 'spawn_worker' && data.worker) foldWorkerIntoMain(data.worker);
  // TICKET-DESK-V2B4 ②：回合中每次 tool.complete 后轻量刷新上下文药丸
  // （context.stats 只读毫秒级估算，无轮询；配合后端活引擎取数，药丸随回合实时涨）
  refreshCtxStats();
  // 联动：Bobo 读文件 → 自动在项目面板显示
  var name = data ? data.name : '';
  if (name === 'read_local_file') {
    var args = data ? data.arguments || {} : {};
    var fp = (args.filepath || args.path || '').toString();
    if (fp) { openPlugin('project'); showProjectFile(fp); }
  }
  if (name === 'write_obsidian' || name === 'append_obsidian') {
    var fn = (data ? data.arguments || {} : {}).filename || '';
    if (fn) { openPlugin('notes'); }
  }
});
// TICKET-PROFILE-3：档案更新卡 —— 后端 profile.update 事件（PROFILE-2/2b emit，payload:
// {category, entry, diff}）。非工具调用（无 tool_id/状态），不走 addTool 完整工具卡逻辑，
// 做轻量"档案更新卡"：图标 + Edit profile 标题 + diff 红绿块（复用 diffBlock，与 edit_file 同 style）。
on('profile.update', function(data) {
  if (isForeignSession(data)) return;
  var diff = data ? data.diff || '' : '';
  var entry = data ? data.entry || '' : '';
  if (!entry && !diff) return;
  var card = document.createElement('div');
  card.className = 'profile-update-card';
  card.setAttribute('data-tool', 'profile_update');
  card.innerHTML = toolIcon('profile_update') +
    '<span class="profile-update-title">' + esc('Edit profile') + '</span>';
  if (diff) {
    var dwrap = document.createElement('div');
    dwrap.className = 'profile-update-diff';
    dwrap.innerHTML = diffBlock(diff);
    card.appendChild(dwrap);
  }
  chatEl.appendChild(card);
  chatEl.scrollTop = chatEl.scrollHeight;
});
// TICKET-SKILL-ACTIVE-2：skill 激活卡 —— 后端 skill.activate 事件（SKILL-ACTIVE-2
// injector emit，payload: {skill_name}，每轮一次防刷屏）。非工具调用，轻量卡：
// 图标 + Skill 标题 + 名称摘要（与 profile.update 卡同款，无 diff 块）。
on('skill.activate', function(data) {
  if (isForeignSession(data)) return;
  var name = data ? data.skill_name || '' : '';
  if (!name) return;
  var card = document.createElement('div');
  card.className = 'skill-activate-card';
  card.setAttribute('data-tool', 'skill_activate');
  card.innerHTML = toolIcon('skill_activate') +
    '<span class="skill-activate-title">' + esc('Skill') + '</span>' +
    '<span class="skill-activate-summary">' + esc(name) + '</span>';
  chatEl.appendChild(card);
  chatEl.scrollTop = chatEl.scrollHeight;
});
// TICKET-D1d ④: 模式徽标 —— AUTO / OFFICE 实时指示（对齐 TUI 底部状态栏）
on('session.auto_state', function(data) { if (isForeignSession(data)) return; setMode(data && data.on ? 'auto' : ''); });
on('session.office_state', function(data) { if (isForeignSession(data)) return; setMode(data && data.on ? 'office' : ''); });
// TICKET-COMPUTER-USE-ROUTE：COMPUTER use 开关状态实时同步（toggle on/off，不联动状态徽标）
on('session.computer_use_state', function(data) { if (isForeignSession(data)) return; var cut = document.getElementById('computer-use-toggle'); if (cut) { cut.classList.toggle('on', !!(data && data.on)); cut.textContent = (data && data.on) ? 'COMPUTER ✓' : 'COMPUTER'; } });
// TICKET-GUI-F1 (F1-3): 引擎内部诊断类状态不进消息区 —— thinking 阶段（tool_filter/calling_llm/
// executing_tools/executing/continuing/compressing/cross_search）由 engine_adapter 转发为
// status.update，TUI 侧只在思考区/状态栏快闪；GUI 若 addStatus 会每轮永久堆积成状态轰炸。
// 统一按 kind 黑名单过滤 + 文本正则兜底（防御文本变化），保留 undo/rate_limit/turn_summary 等用户可见状态。
var STATUS_DIAG_KINDS = {
  tool_filter: 1, calling_llm: 1, executing_tools: 1, executing: 1,
  continuing: 1, compressing: 1, cross_search: 1
};
on('status.update', function(data) {
  if (isForeignSession(data)) return;
  var t = data ? data.text || '' : ''; if (!t) return;
  var kind = data ? data.kind || '' : '';
  if (STATUS_DIAG_KINDS[kind]) return;
  // F1-3 文本兜底：诊断类文本（kind 缺失或新 phase）同样拦截
  if (/^加载 \d+ 个工具 \(/.test(t)) return;
  if (/^准备执行 \d+ 个工具/.test(t) || /^并行执行 \d+ 个工具/.test(t)) return;
  if (t === '工具执行完成' || t === '正在思考...' || /^已用 \d+\/\d+ 步$/.test(t)) return;
  if (/^正在压缩历史上下文/.test(t) || /^搜索 '.*' 跨平台/.test(t)) return;
  // heartbeat：周期性活性提示（15s 一次）——F2-4 单条原地更新：遍历找最后一条
  // "仍在工作" status（中间可能有工具卡/消息插入，只看 lastElementChild 会漏），
  // 找到即原地替换绝不追加新条，杜绝 owner 截图的多条心跳并存
  if (kind === 'heartbeat' || t.indexOf('仍在工作') === 0) {
    var sts = chatEl.querySelectorAll('.status');
    var hbEl = null;
    for (var hi = sts.length - 1; hi >= 0; hi--) {
      if (sts[hi].textContent.indexOf('仍在工作') === 0) { hbEl = sts[hi]; break; }
    }
    if (hbEl) { if (hbEl.textContent !== t) { hbEl.textContent = t; chatEl.scrollTop = chatEl.scrollHeight; } return; }
  }
  addStatus(t);
});
var _everConnected = false;
on('backend.exited', function(data) {
  setConnected(false);
  debug('Backend disconnected' + (data && data.code ? ' (code ' + data.code + ')' : ''));
  // TICKET-DESK-V2A：已连接过 → 断连全屏态（明确告知 + 重启指引）；
  // 从未连接过（首启无 key）→ 保留原 setup 配置屏
  if (_everConnected) { showOverlay('disconnected'); }
  else { showSetup(); }
});

// ── Setup screen (first-run config) ──
function showSetup() {
  var el = document.getElementById('setup-screen');
  if (el) el.style.display = 'flex';
}
function hideSetup() {
  var el = document.getElementById('setup-screen');
  if (el) el.style.display = 'none';
}

document.getElementById('setup-save').onclick = function() {
  var key = document.getElementById('setup-key').value.trim();
  var url = document.getElementById('setup-url').value.trim();
  var model = document.getElementById('setup-model').value.trim();
  var msg = document.getElementById('setup-msg');
  if (!key) { msg.textContent = 'Please enter API Key'; return; }
  msg.textContent = 'Saving...';
  // TICKET-D1d ⑦-B: api_key 走 setup.submit（后端权威写盘 BOBO_DATA_DIR/.env + B3 热生效，零重启）
  call('setup.submit', { provider: 'deepseek', api_key: key }).then(function(res) {
    if (res && res.ok === false) {
      msg.textContent = 'Save failed: ' + (res.error || 'Unknown error');
      return;
    }
    // model 走 config.set（权威 key: API_MODEL_NAME，热生效）
    if (model && model !== 'deepseek-chat') {
      call('config.set', { key: 'model', value: model });
    }
    // base_url 无 RPC 通道 → 走保留的 save-env（仅写该字段；TICKET-D1d ⑦-A 已令其跟随数据目录）
    if (url && window.boboAPI && window.boboAPI.saveEnv) {
      window.boboAPI.saveEnv({ DEEPSEEK_API_BASE_URL: url });
      msg.textContent = 'Saved, restarting...';
      setTimeout(function() { hideSetup(); }, 1500);
    } else {
      msg.textContent = 'Saved';
      setTimeout(function() { hideSetup(); }, 800);
    }
  });
};

var _approvalSid = null;   // TICKET-GUI-F10：当前审批弹窗来源会话（应答回正确会话，防切窗错配）
on('approval.request', function(data) {
  // TICKET-GUI-F10：审批是引擎全局单队列（不吞弹窗），但应答必须回弹窗来源会话，
  // 不能跟 currentSessionId —— 否则 A 会话的审批会在切到 B 后被错配到 B
  _approvalSid = (data && data.session_id) || currentSessionId;
  // TICKET-D1d ③: 模态卡替代原生 confirm —— 立即呈现、操作预览、无超时自动拒绝
  var cmd = data.command || data.description || 'unknown';
  var desc = data.description || '';
  document.getElementById('approval-cmd').textContent = cmd;
  document.getElementById('approval-desc').textContent = desc;
  document.getElementById('approval-overlay').classList.add('open');
});
// 批准/拒绝：直接 send（不经 call() 的 120s resolve 包装）——保证送达，杜绝瞎闸
function approvalRespond(choice) {
  document.getElementById('approval-overlay').classList.remove('open');
  if (window.boboAPI) {
    window.boboAPI.send({ jsonrpc:'2.0', id:'approval-resp-'+(++reqId), method:'approval.respond', params:{ session_id: _approvalSid, choice: choice } });
  }
  if (choice === 'deny') addStatus('Operation denied');
}
document.getElementById('approval-allow').onclick = function() { approvalRespond('once'); };
document.getElementById('approval-deny').onclick = function() { approvalRespond('deny'); };
on('gateway.error', function(data) {
  if (isForeignSession(data)) return;
  addStatus('❌ ' + (data.message || 'Unknown error').substring(0, 200));
  debug('Error: ' + (data.message || '').substring(0, 60));
  // TICKET-DESK-V2A：后端错误 toast 接入点
  showToast('fail', (data.message || 'Backend error').substring(0, 120));
});

// ── Fallback: if gateway.ready hasn't fired within 5s, poll backend ──
var readyFallbackTimer = setTimeout(async function() {
  if (connected) return;
  debug('Waiting for backend...');
  for (var attempt = 0; attempt < 5; attempt++) {
    if (connected) return;
    var r = await call('setup.status', {});
    if (r && typeof r === 'object' && !r.error) {
      // Backend is alive despite missing gateway.ready
      _everConnected = true;
      setConnected(true);
      // TICKET-GUI-F14：gateway.ready 丢失时 fallback 接管——四行无依赖初始化同样必须执行
      //（否则插件区空白/药丸恒 0%/命令目录不加载，与 loadSession 拖死同症状）
      renderPluginList();
      document.getElementById('body-plugin').classList.add('closed');
      document.getElementById('arr-plugin').classList.add('closed');
      refreshCtxStats();
      loadSlashCatalog();
      await loadSessions();
      if (sessions.length > 0) {
        currentSessionId = sessions[0].id;
        call('session.activate', { session_id: sessions[0].id });
        renderSessions();
        renderBusyUI();   // V4B⓪：fallback 路径同样按当前会话刷新忙碌态
      } else {
        await newChat();
      }
      debug('Connected ✓');
      inputEl.focus();
      // TICKET-DESK-V2A：fallback 恢复成功同样收覆盖层 + toast
      hideOverlay();
      showToast('success', 'Connection restored');
      return;
    }
    await new Promise(function(r2) { setTimeout(r2, 2000); });
  }
  if (!connected) {
    debug('Backend unavailable');
    // TICKET-DESK-V2A：5 次轮询仍无后端 → 连接失败全屏态（错误图标 + 重试按钮）
    showOverlay('failed');
  }
}, 5000);
