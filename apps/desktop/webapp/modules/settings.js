// ── Settings ────────────────────────────────────────────────────────────
// Tab switching
document.querySelectorAll('.settings-tab').forEach(function(tab) {
  tab.addEventListener('click', function() {
    document.querySelectorAll('.settings-tab').forEach(function(t) { t.classList.remove('active'); });
    this.classList.add('active');
    document.querySelectorAll('.settings-page').forEach(function(p) { p.style.display = 'none'; });
    var page = document.getElementById('page-' + this.getAttribute('data-tab'));
    if (page) page.style.display = 'block';
  });
});

// Open settings
// TICKET-PROVIDER-ADAPTER：provider/model 下拉动态渲染——model.options RPC
// 返回全部 provider（provider.py 唯一事实源），不再前端硬编码（新增 provider
// 自动出现，如 kimi/lmstudio）。
function populateProviderSelect(data) {
  var sel = document.getElementById('cfg-provider');
  var prev = sel.value;
  sel.innerHTML = '';
  (data.providers || []).forEach(function(p) {
    var opt = document.createElement('option');
    opt.value = p.slug; opt.textContent = p.name + (p.is_current ? ' (current)' : '');
    if (p.slug === prev || p.is_current) opt.selected = true;
    sel.appendChild(opt);
  });
  // 填充当前 provider 的模型列表
  var cur = (data.providers || []).find(function(p) { return p.slug === sel.value; });
  var msel = document.getElementById('cfg-model');
  var mprev = msel.value;
  msel.innerHTML = '';
  ((cur && cur.models) || []).forEach(function(m) {
    var opt = document.createElement('option'); opt.value = m; opt.textContent = m;
    if (m === mprev || m === data.model) opt.selected = true;
    msel.appendChild(opt);
  });
  // TICKET-PROVIDER-ADAPTER：API Key 表格渲染（每个 provider 一行）
  renderApiKeyTable(data);
}

// API Key 表格：左边 provider 名（+已配置状态），右边 key 输入框。
// key 存 JS 全局 apikeys（Save 时逐个提交），本地 provider 显示"无需 key"。
var apikeys = {};
function renderApiKeyTable(data) {
  var tbl = document.getElementById('apikey-table');
  if (!tbl) return;
  var html = '';
  (data.providers || []).forEach(function(p) {
    var needsKey = p.auth_type === 'api_key';
    html += '<div class="apikey-row">' +
      '<span class="apikey-name">' + esc(p.name) +
      (p.authenticated ? ' <span class="apikey-dot" title="Configured">●</span>' : '') +
      '</span>';
    if (needsKey) {
      html += '<input class="apikey-input" type="password" data-provider="' + p.slug +
        '" autocomplete="new-password" ' +
        'placeholder="' + (p.authenticated ? '•••••• (leave blank to keep)' : 'Enter API Key') + '" />';
    } else {
      html += '<span class="apikey-none">No API key needed</span>';
    }
    html += '</div>';
  });
  tbl.innerHTML = html;
  // 收集输入框引用
  apikeys = {};
  tbl.querySelectorAll('.apikey-input').forEach(function(inp) {
    inp.addEventListener('input', function() { apikeys[inp.dataset.provider] = inp.value.trim(); });
  });
}
document.getElementById('settings-icon').onclick = function() {
  // 动态拉 provider 列表（适配层：注册即出现在设置页）
  call('model.options', {}).then(function(r1) {
    if (r1 && r1.providers) {
      populateProviderSelect(r1);
      document.getElementById('cfg-apikey').placeholder = 'Enter API Key';
    } else {
      // 兜底：RPC 失败时退回到旧 setup.status 路径
      call('setup.status', {}).then(function(r0) {
        document.getElementById('cfg-provider').value = (r0 && r0.provider) || 'deepseek';
        document.getElementById('cfg-apikey').placeholder = (r0 && r0.provider_configured) ? 'Configured' : 'Enter API Key';
        document.getElementById('cfg-provider').dispatchEvent(new Event('change'));
      });
    }
  });
  document.getElementById('settings-modal').classList.add('open');
};
// TICKET-PROFILE-4 v2：设置页 Profile 仪表盘 —— 区块 1 可编辑编辑器（白底 +
// Save，用户绝对权威）+ 区块 2 更新历史（独立，GitHub 式，按来源着色）。
function renderProfileUserMd(userMd) {
  var label = document.getElementById('profile-edit-label');
  var area = document.getElementById('profile-edit-area');
  if (!label || !area) return;
  // 页面文案走 \u 转义（DESK-P2 金标准：index.html 非注释区零中文）
  label.textContent = 'User Profile (Editable)';
  // 当前用户模型（可编辑）
  area.value = userMd || '';
}
function fmtProfileTs(ts) {
  var d = new Date(ts * 1000);
  function p(n) { return n < 10 ? '0' + n : '' + n; }
  return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' +
         p(d.getHours()) + ':' + p(d.getMinutes());
}
function profileDiffHtml(diff) {
  var escDiff = esc(diff || '');
  if (escDiff.indexOf('+ ') === 0) return '<span class="profile-diff-add">' + escDiff + '</span>';
  if (escDiff.indexOf('- ') === 0) return '<span class="profile-diff-del">' + escDiff + '</span>';
  var parts = escDiff.split(' → ');
  if (parts.length === 2) {
    return '<span class="profile-diff-del">' + parts[0] + '</span> → ' +
           '<span class="profile-diff-add">' + parts[1] + '</span>';
  }
  return '<span>' + escDiff + '</span>';
}
function renderProfileHistory(versions) {
  var el = document.getElementById('profile-history');
  if (!el) return;
  // 页面文案走 \u 转义（DESK-P2 金标准：index.html 非注释区零中文）
  var labelHist = 'Update History';
  var emptyHist = 'No updates yet \u2014 when bobo learns a new preference, it will appear here.';
  var html = '<div class="settings-sec-label">' + labelHist + '</div>';
  if (!versions || versions.length === 0) {
    el.innerHTML = html + '<div class="profile-empty">' + emptyHist + '</div>';
    return;
  }
  versions.forEach(function(v) {
    var ts = v.ts || 0;
    var src = v.signal_source || 'user';
    // 着色：绿=auto 添加 / 红=auto 删除 / 黄=用户手动编辑（diff 式整行高亮）
    var rowCls = 'profile-history-row';
    var diffHtml = profileDiffHtml(v.diff || v.entry || '');
    if (src === 'user_edit') {
      rowCls += ' src-user';
      diffHtml = '<span class="profile-diff-user">' + esc(v.diff || v.entry || '') + '</span>';
    }
    html += '<div class="' + rowCls + '">' +
      '<span class="profile-history-time">' + fmtProfileTs(ts) + '</span>' +
      '<span class="profile-cat-badge">' + esc(v.category || '') + '</span>' +
      '<span class="profile-history-diff">' + diffHtml + '</span>' +
      '<button class="profile-rollback-btn" data-ts="' + ts + '" title="Roll back">\u27f2</button>' +
      '</div>';
  });
  el.innerHTML = html;
  el.querySelectorAll('.profile-rollback-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var ts = Number(btn.getAttribute('data-ts'));
      var row = btn.closest('.profile-history-row');
      var timeText = row ? row.querySelector('.profile-history-time').textContent : '';
      // 回滚到 <时间> 的版本？（\u 转义，DESK-P2）
      if (!window.confirm('Roll back to ' + timeText + '?')) return;
      call('profile.rollback', { ts: ts }).then(function(r) {
        if (r && r.message) { window.alert('Rollback failed: ' + r.message); return; }
        renderProfileUserMd(r ? r.user_md || '' : '');
        renderProfileHistory(r ? r.versions || [] : []);
      });
    });
  });
}
function loadProfilePanel() {
  call('profile.get', {}).then(function(r) {
    if (r && r.message) { window.alert('Load failed: ' + r.message); return; }
    renderProfileUserMd(r ? r.user_md || '' : '');
    renderProfileHistory(r ? r.versions || [] : []);
  });
}
// 点击 Profile tab 时懒加载（tab 切换 JS 已通用，不动）
var profileTabEl = document.querySelector('.settings-tab[data-tab="profile"]');
if (profileTabEl) profileTabEl.addEventListener('click', loadProfilePanel);
// TICKET-PROFILE-4 v2：Save 按钮 —— 用户手动编辑 USER.md 后保存（绝对权威）
var profileSaveBtn = document.getElementById('profile-save-btn');
var profileEditArea = document.getElementById('profile-edit-area');
var profileSaveHint = document.getElementById('profile-save-hint');
if (profileSaveBtn) profileSaveBtn.addEventListener('click', function() {
  if (!profileEditArea) return;
  var newMd = profileEditArea.value;
  profileSaveBtn.disabled = true;
  call('profile.save', { user_md: newMd }).then(function(r) {
    profileSaveBtn.disabled = false;
    if (r && r.message) {
      // 保存失败
      window.alert('Save failed: ' + r.message);
      return;
    }
    renderProfileUserMd(r ? r.user_md || '' : '');
    renderProfileHistory(r ? r.versions || [] : []);
    if (profileSaveHint) {
      // 已保存（黄色=用户手动编辑）
      profileSaveHint.textContent = 'Saved (yellow = your manual edit)';
      setTimeout(function() { profileSaveHint.textContent = ''; }, 3000);
    }
  });
});
// Provider → model linkage
// TICKET-PROVIDER-ADAPTER：切换 provider 时动态拉该 provider 的模型列表
//（不再前端硬编码——新增 provider 的模型自动出现）
document.getElementById('cfg-provider').addEventListener('change', function() {
  var slug = this.value;
  call('model.options', {}).then(function(r1) {
    if (!r1 || !r1.providers) return;
    var cur = r1.providers.find(function(p) { return p.slug === slug; });
    var sel = document.getElementById('cfg-model');
    var prev = sel.value;
    sel.innerHTML = '';
    ((cur && cur.models) || []).forEach(function(m) {
      var opt = document.createElement('option'); opt.value = m; opt.textContent = m;
      if (m === prev || m === r1.model) opt.selected = true;
      sel.appendChild(opt);
    });
  });
});
document.getElementById('settings-close').onclick = function() {
  document.getElementById('settings-modal').classList.remove('open');
};
document.getElementById('settings-save').onclick = function() {
  var model = document.getElementById('cfg-model').value;
  var provider = document.getElementById('cfg-provider').value;
  // TICKET-PROVIDER-ADAPTER：provider 选择必须保存——config.set 支持
  // "<model> --provider <provider>" 格式（configs.py 解析，写 BOBO_PROVIDER +
  // API_MODEL_NAME 到 .env + 热生效）。
  var steps = [];
  // 1. provider + model 写入（model 没选时只发 provider 占位）
  var modelArg = model || 'deepseek-v4-flash';
  steps.push(call('config.set', { key: 'model', value: modelArg + ' --provider ' + provider })
    .catch(function() { return null; }));
  // 2. API Key 表格：每个填了 key 的 provider 逐个提交（留空的跳过=保留原值；
  //    重新填 = 替换原值——用户要求的替换语义）
  Object.keys(apikeys).forEach(function(slug) {
    var k = apikeys[slug];
    if (k) steps.push(call('setup.submit', { provider: slug, api_key: k }).catch(function() { return null; }));
  });
  Promise.all(steps).then(function() {
    addStatus('Saved — provider applied');
    document.getElementById('settings-modal').classList.remove('open');
  });
};
document.getElementById('settings-clear').onclick = function() {
  if (!confirm('Delete all sessions? This cannot be undone.')) return;
  sessions.forEach(function(s) {
    call('session.delete', { session_id: s.id });
  });
  sessions = [];
  currentSessionId = null;
  clearChat();
  renderSessions();
  renderBusyUI();   // V4B⓪：无当前会话 → 空闲态（清理全局忙碌残留）
  addStatus('All sessions deleted');
  document.getElementById('settings-modal').classList.remove('open');
};

// ── Session search ──────────────────────────────────────────────────────
document.getElementById('session-search').addEventListener('input', function() {
  renderSessions(this.value);
});

// ── Keyboard shortcuts ──────────────────────────────────────────────────
document.addEventListener('keydown', function(e) {
  var mod = e.metaKey || e.ctrlKey;
  if (e.key === 'n' && mod) { e.preventDefault(); newChat(); }
  if (e.key === ',' && mod) { e.preventDefault(); document.getElementById('settings-icon').click(); }
  if (e.key === 'Escape') {
    // TICKET-DESK-V2B3：命令面板开着时 Esc 优先关闭（不触发明细卡/中断）
    var spEl = document.getElementById('slash-panel');
    if (spEl && spEl.style.display !== 'none') { spEl.style.display = 'none'; return; }
    // TICKET-DESK-V2B：明细卡开着时 Esc 优先收起（不触发中断）
    var ctxDet = document.getElementById('ctx-stats-detail');
    if (ctxDet && ctxDet.style.display !== 'none') { ctxDet.style.display = 'none'; }
    else {
      // TICKET-GUI-F24：Request 面板开着时 Esc 收起（优先级：命令面板→明细卡→Request→中断）
      var reqP = document.getElementById('request-panel');
      if (reqP && reqP.style.display !== 'none') { reqP.style.display = 'none'; }
      else { stopThinking(); }
    }
  }
});

// ── Auto-hide sidebar on narrow window ──────────────────────────────────
var sidebarEl = document.getElementById('sidebar');
var sidebarOpen = true;
function checkSidebar() {
  if (window.innerWidth < 640 && sidebarOpen) {
    sidebarEl.classList.add('closed'); sidebarOpen = false;
  } else if (window.innerWidth >= 640 && !sidebarOpen) {
    sidebarEl.classList.remove('closed'); sidebarOpen = true;
  }
}
window.addEventListener('resize', checkSidebar);
checkSidebar();

// ── HTML Preview ────────────────────────────────────────────────────
function openPreview(cid) {
  var code = _codeStore[cid];
  if (!code) return;
  document.getElementById('preview-overlay').classList.add('open');
  document.getElementById('preview-panel').classList.add('open');
  document.getElementById('preview-iframe').srcdoc = code;
}
document.getElementById('preview-close').onclick = function() {
  document.getElementById('preview-overlay').classList.remove('open');
  document.getElementById('preview-panel').classList.remove('open');
  var ifr = document.getElementById('preview-iframe');
  ifr.srcdoc = '';
};
document.getElementById('preview-overlay').onclick = function() {
  document.getElementById('preview-close').click();
};

// ── Session search ──────────────────────────────────────────────────────

// ═══ TICKET-DESK-TEL：Telescope 引擎实况观测台（纯只读：只订阅事件、只读渲染，零干涉）═══
// 铁律：不改引擎/gateway/聊天区任何现有行为；数据全部来自真实事件流
// （message.start/delta/complete + tool.start/complete + task_ledger + usage 预算审计）；
// 面板内容一律经 mdReply()（marked+DOMPurify）管线，禁止 raw JSON / raw 日志直接上屏。

var _telEl = null;        // 面板容器（right-content 内）
var _telRound = 0;        // 轮次号（message.start 递增）
var _telRounds = [];      // 已归档轮历史（每轮结束推进来；上限 50 防无限增长）—— 战报从头可读
var _telState = null;     // 当前轮观测状态
var _telInitDone = false;
var _telModalEl = null;   // diff 模态层（同时只开一个）
var _telDirty = false;    // delta 节流：待渲染标记
var _telRaf = null;       // delta 节流：rAF 句柄
var _telTab = 'battle';   // COST-1b：面板页签（battle=战报 | cost=消耗）

// 分类映射：同 category 的工具调用进同一张活表格（Skills / Memory / Tools）
function _telCat(name) {
  if (name === 'save_skill' || name === 'load_skill') return 'Skills';
  if (name === 'search_memory' || name === 'save_memory') return 'Memory';
  return 'Tools';
}

// 写入/编辑类工具（结果格渲染"查看 diff"链接，弹模态层）
function _telIsWriteTool(name) {
  return name === 'edit_file' || name === 'write_obsidian' || name === 'append_obsidian' ||
         name === 'file_operation' || name === 'write';
}

// diff 增删行统计（供"写入 +N/−M 行"人话结果）
function _telDiffStats(diff) {
  var add = 0, del = 0;
  String(diff || '').split('\n').forEach(function(l) {
    if (l.indexOf('+++') === 0 || l.indexOf('---') === 0) return;
    if (l.indexOf('+') === 0) add++;
    else if (l.indexOf('-') === 0) del++;
  });
  return { add: add, del: del };
}

// 只读：取聊天区最后一条用户消息原文（不修改任何 DOM）
function _telLastUserPrompt() {
  if (!chatEl) return '';
  var umsgs = chatEl.querySelectorAll('.msg.user');
  if (!umsgs || !umsgs.length) return '';
  var lastU = umsgs[umsgs.length - 1];
  var txtEl = lastU.querySelector ? lastU.querySelector('.txt') : null;
  return (txtEl && txtEl.textContent) ? String(txtEl.textContent).trim() : '';
}

function _telBlankState() {
  return {
    round: _telRound,
    prompt: _telLastUserPrompt(),
    understand: '', deltaBuf: '',
    ledger: null,                                   // {rows:[{title,status}]}
    calls: { Skills: [], Memory: [], Tools: [] },   // 活表格：每行 {name,args,result,dur,diff,error}
    terminal: [],                                   // [{command,output,duration,exitCode}]
    files: 0, addLines: 0, delLines: 0,
    tests: '', concl: '', usage: null,
    summaryDone: false,
  };
}

// 归档判定：轮次必须有真实观测内容才进历史（空轮/首开空态不归档）
function _telStateHasContent(st) {
  if (!st) return false;
  if (st.prompt) return true;
  if (st.ledger && st.ledger.rows && st.ledger.rows.length) return true;
  if (st.terminal.length) return true;
  if (st.calls.Tools.length || st.calls.Skills.length || st.calls.Memory.length) return true;
  if (st.summaryDone) return true;
  return false;
}

function _telNewRound() {
  // 上一轮有内容 → 归档进历史（整面板可读成连贯战报；上限 50 轮丢最旧）
  if (_telStateHasContent(_telState)) {
    _telRounds.push(_telState);
    if (_telRounds.length > 50) _telRounds.shift();
  }
  _telRound++;
  _telState = _telBlankState();
}
