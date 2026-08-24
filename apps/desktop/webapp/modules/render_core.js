// ── Messages ───────────────────────────────────────────────────────────
function clearChat() { chatEl.innerHTML = ''; welcomeEl.style.display = 'flex'; }

// TICKET-COST-5：动态块渲染剥离（方案 D）——历史/归档显示【COST-2 动态块】治理。
// 根因：core/injector.py:750-765 动态块附加到本轮 user 消息 content 前部并写回
// history（前缀稳定化、缓存命中 ~100% 的机制），副作用是历史 user 消息含内部
// 上下文。方案 D：存储/请求零改动（不破坏前缀稳定），渲染层剥离。格式：
//   【COST-2 动态块】\n<块1>\n\n<块2>...\n\n<原文>
// 原文分隔 = 最后一个 \n\n（dyn_text 内部块间也是 \n\n，故用 lastIndexOf
// 而非第一个分隔——锚点初版写"第一个"有误，L14 读源码修正）。
// 只剥以标记开头的消息；原文内出现标记字样不误剥（indexOf !== 0 短路）。
function stripDynBlock(text) {
  if (!text || typeof text !== 'string') return text;
  if (text.indexOf('【COST-2 动态块】') !== 0) return text;
  var i = text.lastIndexOf('\n\n');
  if (i < 0) return '';
  return text.slice(i + 2);
}

function addMsg(role, text, id, append, image) {
  // TICKET-VISION-CHAT-UPLOAD：content 可能是多模态 list（text + image_url）
  if (Array.isArray(text)) {
    var _ta = '';
    for (var i = 0; i < text.length; i++) {
      var _p = text[i];
      if (_p && _p.type === 'text') _ta += (_p.text || '');
      else if (_p && _p.type === 'image_url') image = (_p.image_url && _p.image_url.url) || '';
    }
    text = _ta;
  }
  // TICKET-DESK-V4: 用户指令只读广播给小窗（投影数据源；不改任何渲染行为/状态）
  // V4B: 带会话 sid（小窗按钉选过滤，A 的指令不泄漏到钉 B 的小窗）
  if (role === 'user' && text && typeof window !== 'undefined' && window.boboAPI && window.boboAPI.widgetUserMsg) {
    window.boboAPI.widgetUserMsg(text, currentSessionId);
  }
  welcomeEl.style.display = 'none';
  // TICKET-COST-5：user 消息渲染层剥离动态块（历史重放 renderFullHistory /
  // renderArchivedMessages / 窗口化路径 / 实时防御性，一处覆盖；无标记原样返回
  // 零影响；widgetUserMsg 广播已用原始 text，投影语义不变）
  if (role === 'user' && text) text = stripDynBlock(text);
  // TICKET-DESK-V2C12 (C1)：仅助手正文气泡（bobo）走完整 markdown 管线；用户消息保持既有简渲染
  var render = (role === 'bobo') ? mdReply : md;
  var existing = document.getElementById(id);
  if (existing) {
    var t = existing.querySelector('.txt');
    t.innerHTML = append ? t.innerHTML + render(text) : render(text);
    return;
  }
  // TICKET-VISION-CHAT-UPLOAD：图上文下（image 在上，文字在下）
  var imgHtml = (image && role === 'user') ? '<img class="chat-img" src="' + image + '" alt="image"/>' : '';
  var div = document.createElement('div'); div.id = id; div.className = 'msg ' + role;
  div.innerHTML = '<div class="who">' + (role==='user'?'You':'Bobo') + '</div>' + imgHtml + '<div class="txt">' + render(text) + '</div>';
  chatEl.appendChild(div); chatEl.scrollTop = chatEl.scrollHeight;
  return div;
}
var toolResults = {};
var toolIdCounter = 0;
// F2-3: 工具长链聚合状态（同回合 >3 步时前 3 步收进聚合卡，最新一步保持展开可见）
var roundToolEls = [];        // 本轮工具卡元素（未聚合部分）
var roundAggregated = false;  // 本轮是否已聚合
var roundTotalCount = 0;      // 本轮工具总步数
var roundAggregateHead = null;// 聚合卡标题元素（实时更新步数）

// TICKET-GUI-F8：工具友好名映射提升为模块级（历史工具 diff 渲染 renderHistToolDiff 复用）
var TOOL_FRIENDLY = {
  'file_operation': 'Write file', 'write_obsidian': 'Write note', 'append_obsidian': 'Append note',
  'read_local_file': 'Read file', 'read_obsidian': 'Read note',
  'grep_code': 'Search code', 'search_code': 'Search code', 'search_obsidian': 'Search note',
  'code_execution': 'Run code', 'execute_terminal': 'Terminal',
  'edit_file': 'Edit file', 'run_tests': 'Run tests',
  'web_search': 'Web search', 'web_fetch': 'Fetch page', 'web_extract': 'Extract content',
  'git_status': 'Git status', 'github_create_pr': 'Create PR', 'github_pr_diff': 'PR diff',
  'index_project': 'Index project', 'review_diff': 'Review code',
  'cross_search': 'Cross-search', 'cross_project_search': 'Cross-project search',
  'code_to_obsidian': 'Save knowledge', 'review_to_obsidian': 'Save review',
  'save_memory': 'Save memory', 'search_memory': 'Search memory',
  'get_current_time': 'Get time', 'list_directory': 'List directory',
  'notion_search': 'Search Notion', 'notion_create_page': 'Create Notion page',
  'search_emails': 'Search email', 'send_notification': 'Send notification',
  // TICKET-PROFILE-3：档案更新（后端 profile.update 事件，非工具调用）
  'profile_update': 'Edit profile',
  // TICKET-SKILL-ACTIVE-2：skill 激活（后端 skill.activate 事件，非工具调用）
  'skill_activate': 'Skill',
};

// TICKET-DESK-V2D25：细线 SVG 图标映射（D2.5-1）——14px / 1.25px 描边 / fill:none /
// currentColor 继承文字色；映射集中本对象，未知工具回退 _default 小方块（不许空白）
var TOOL_ICONS = {
  'execute_terminal': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="1.75" y="2.75" width="10.5" height="8.5" rx="1.5"/><path d="M4.25 5.25 L6 7 L4.25 8.75"/><path d="M7.5 8.75 h2.25"/></svg>',
  'computer_use': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="1.75" y="2.25" width="10.5" height="7" rx="1.25"/><path d="M4.5 11.25 h5"/><path d="M7 9.5 v1.75"/><path d="M9.2 4.9 l-0.5 3.4 1.2-1.0 0.9 1.3"/></svg>',
  'read_local_file': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 1.75 h3.5 l3.25 3.25 V12.25 H4 Z"/><path d="M7.25 1.75 v3.5 h3.5"/></svg>',
  'edit_file': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.1 11.4 L3.65 8.9 8.9 3.65 c.35-.35 .92-.35 1.27 0 l.18.18 c.35.35 .35.92 0 1.27 L5.1 10.35 l-2.5.65 z"/><path d="M2.3 12.2 h9.4"/></svg>',
  'grep_code': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="6" cy="6" r="3.4"/><path d="M8.6 8.6 L11.5 11.5"/></svg>',
  'save_memory': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2.5" y="2.5" width="9" height="9" rx="1.75"/><path d="M7 4.9 L9.1 7 L7 9.1 L4.9 7 Z"/></svg>',
  'load_result': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2.5" y="2.5" width="9" height="9" rx="1.75"/><path d="M7 4.9 L9.1 7 L7 9.1 L4.9 7 Z"/></svg>',
  'task_ledger': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 4.25 h8 M3 7 h8 M3 9.75 h8"/></svg>',
  'run_tests': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.75 7.5 L5.5 10.25 L11.25 3.75"/></svg>',
  'web_search': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="7" cy="7" r="4.25"/><path d="M2.75 7 h8.5 M7 2.75 c-1.2 1.35 -1.2 6.15 0 8.5 M7 2.75 c1.2 1.35 1.2 6.15 0 8.5"/></svg>',
  // TICKET-PROFILE-3：档案更新卡图标 —— 人形 + 铅笔（14px / 1.25px 描边，与 edit_file 同风格）
  'profile_update': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="4.4" cy="4.3" r="1.55"/><path d="M2.5 10.6 c0-1.4 1.3-2.3 3-2.3 c1.7 0 3 .9 3 2.3"/><path d="M8.7 8.5 L9.05 6.9 L11.7 4.25 c.35-.35 .92-.35 1.27 0 l.18.18 c.35.35 .35.92 0 1.27 L10.55 8.25 l-1.6 .45 z"/><path d="M8.4 9.1 h3.5"/></svg>',
  // TICKET-SKILL-ACTIVE-2：skill 激活卡图标 —— 打开的书 + 中缝（14px / 1.25px 描边，同款细线）
  'skill_activate': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2.6 3.1 c1.4-0.2 2.9 0.1 4.4 1.1 c1.5-1 3-1.3 4.4-1.1 v7.6 c-1.4-0.2 -2.9 0.1 -4.4 1.1 c-1.5-1 -3-1.3 -4.4-1.1 Z"/><path d="M7 4.2 v7.6"/></svg>',
  '_default': '<svg class="tool-ic" viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="8" height="8" rx="1.25"/></svg>'
};
// 图标取映射，未知工具回退 _default（不许空白）；reduced-motion 下运行卡不加 shimmer class
function toolIcon(name) { return TOOL_ICONS[name] || TOOL_ICONS['_default']; }
function prefersReducedMotion() {
  return !!(typeof window !== 'undefined' && window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches);
}

function addTool(name, context, toolId) {
  welcomeEl.style.display = 'none';
  if (thinkBoxEl) {
    thinkBoxEl.querySelector('.think-label').innerHTML = 'thinking';
    thinkBoxEl.classList.add('done');
  }

  // Friendly names
  var friendly = TOOL_FRIENDLY[name] || name;

  toolIdCounter++;
  var uniqueId = toolId + '-' + toolIdCounter;
  var div = document.createElement('div'); div.className = 'tool';
  div.id = 'tool-' + uniqueId;
  div.setAttribute('data-tool', toolId);
  // TICKET-DESK-V2D25：状态属性化（data-state），DOM 无 running 裸文本——视觉由 .dot/流光表达
  div.setAttribute('data-state', 'running');
  div.innerHTML = toolIcon(name) +
    '<span class="dot ring"></span>' +
    '<span class="tool-name">' + esc(friendly) + '</span>' +
    (context && context !== name ? '<span class="tool-context">' + esc(context) + '</span>' : '') +
    '<span class="tool-time"></span>' +
    '<span class="tool-toggle" style="display:none">▸</span>' +
    '<div class="tool-result"></div>';
  // TICKET-DESK-V2D25：运行中流光（D2.5-3）——纯 CSS animation，reduced-motion 不加 class
  if (!prefersReducedMotion()) div.classList.add('shimmer');
  div.onclick = function(e) {
    // Don't toggle when clicking result text — allows text selection
    if (e.target.closest('.tool-result')) return;
    var r = div.querySelector('.tool-result');
    if (r) { r.classList.toggle('open'); var t = div.querySelector('.tool-toggle'); if (t) { t.textContent = r.classList.contains('open') ? '▾' : '▸'; t.style.display = 'inline'; } }
  };
  // F4-1: 聚合卡持续吞并 —— 任何时刻屏幕只有两块：聚合卡（吞并所有中间步骤）+ 最新一步摊开
  // 第 1 步直接铺开；第 2 步起建聚合卡；之后每步把"最新一步"收进聚合卡、新一步摊开。
  // 标题"已执行 N 步操作"数字实时涨，点击展开全部考古。回合结束聚合卡保留。
  roundTotalCount++;
  if (roundAggregated && roundAggregateHead && roundToolEls.length > 0) {
    // 已有聚合卡：把当前最新一步收进聚合卡（吞并）
    var aggBody2 = roundAggregateHead.parentNode.querySelector('.tool-agg-body');
    roundToolEls.forEach(function(d) {
      // TICKET-GUI-F6D：写/改类工具（编辑流）不入聚合卡 —— 思考与编辑卡+diff 全程摊开
      if (isWriteToolEl(d)) return;
      var tb2 = swallowThinkBox(d);  // F6C：配对思考框一并移入（思考在前，保持成对）
      if (tb2) aggBody2.appendChild(tb2);
      aggBody2.appendChild(d);
    });
    roundToolEls = [];
  }
  chatEl.appendChild(div);
  if (!roundAggregated && roundTotalCount >= 2) {
    // 第 2 步起建聚合卡：把前一步收进去，最新一步保持摊开。
    // F6D：若全部前步都是写类工具（编辑流），无可吞元素则不建空聚合卡——编辑流全程摊开
    var hasSwallowable = roundToolEls.some(function(d) { return !isWriteToolEl(d); });
    if (hasSwallowable) {
      roundAggregated = true;
      var agg = document.createElement('div'); agg.className = 'tool-agg';
      agg.innerHTML = '<span class="tool-agg-head">Executed ' + roundTotalCount + ' steps <span class="tool-agg-arrow">▸</span></span><div class="tool-agg-body" style="display:none"></div>';
      agg.onclick = function(e) {
        if (e.target.closest('.tool')) return; // 点工具卡本身不折叠（卡内自有展开逻辑）
        var body = this.querySelector('.tool-agg-body');
        if (!body) return;  // 票 SAFETY-1：DOM 结构异常（元素缺失）时跳过，防 textContent 空引用
        var open = body.style.display !== 'none';
        body.style.display = open ? 'none' : 'block';
        var arrowEl = this.querySelector('.tool-agg-arrow');
        if (arrowEl) arrowEl.textContent = open ? '▸' : '▾';  // 票 SAFETY-1：空值守卫（1345 事故行）
      };
      var aggBody = agg.querySelector('.tool-agg-body');
      roundToolEls.forEach(function(d) {
        if (isWriteToolEl(d)) return;  // F6D：写类工具卡与配对思考都留在消息流
        var tb = swallowThinkBox(d);  // F6C：配对思考框一并移入（思考在前，保持成对）
        if (tb) aggBody.appendChild(tb);
        aggBody.appendChild(d);
      });
      roundToolEls = [];
      roundAggregateHead = agg.querySelector('.tool-agg-head');
      chatEl.insertBefore(agg, div);
    }
  }
  if (roundAggregated && roundAggregateHead) {
    roundAggregateHead.textContent = 'Executed ' + roundTotalCount + ' steps ' + (aggHeadArrowText());
  }
  roundToolEls.push(div); // 最新一步保留在消息流，保持摊开可见
  chatEl.scrollTop = chatEl.scrollHeight;
}

// TICKET-GUI-F6D：写/改类工具名单 —— 配对思考不吞并（编辑流思考→编辑卡+diff 全程摊开）
// 读/探查类不在此名单：连续调用照常吞并进聚合卡（F6C 行为）；
// 混合序列按"被吞的那步类型"判定：吞写类步骤时思考留在原地，吞读类步骤时思考一并入卡。
var WRITE_TOOLS = [
  'edit_file', 'file_operation', 'refactor', 'file_writer',
  'write_obsidian', 'append_obsidian', 'copy_to_obsidian', 'copy_to_notion',
  'save_memory', 'save_skill', 'task_ledger', 'bobo_config',
  'notion_setup', 'api_register',
  'github_create_pr', 'github_create_repo', 'github_pr_comment', 'github_setup',
  'bobo_schedule', 'wiki_rebuild',
];
function isWriteToolEl(el) {
  if (!el || !el.classList || !el.classList.contains('tool')) return false;
  var name = el.getAttribute ? (el.getAttribute('data-tool') || '') : '';
  return WRITE_TOOLS.indexOf(name) !== -1;
}

// TICKET-GUI-F6C：工具卡被吞进聚合卡时，其前方紧邻的已折叠思考框一并移入
// （保持"思考→工具"成对，考古展开聚合卡时每步思考与工具绑定可见）。
// 注意：聚合卡插在"最新思考与最新工具"之间（insertBefore(agg, div)），
// 吞并最新一步时其配对思考可能隔着一个聚合卡——向前再找一档。
// TICKET-GUI-F6D：相邻判定跳过状态行（status 类非结构节点），直到撞上
// 思考框/工具卡/正文/聚合卡再判定（owner 实证：状态行打断相邻判定，思考框连排成墙）。
function swallowThinkBox(d) {
  // F6D：写/改类工具（编辑流）思考不吞并 —— 保持摊开（owner 裁决：编辑是创作必须看清每步意图）
  if (isWriteToolEl(d)) return null;
  var prev = d.previousElementSibling;
  while (prev && prev.classList && prev.classList.contains('status')) {
    prev = prev.previousElementSibling;
  }
  if (prev && prev.classList && prev.classList.contains('think-box') &&
      prev.classList.contains('collapsed')) return prev;
  if (prev && prev.classList && prev.classList.contains('tool-agg')) {
    var prev2 = prev.previousElementSibling;
    while (prev2 && prev2.classList && prev2.classList.contains('status')) {
      prev2 = prev2.previousElementSibling;
    }
    if (prev2 && prev2.classList && prev2.classList.contains('think-box') &&
        prev2.classList.contains('collapsed')) return prev2;
  }
  return null;
}

function aggHeadArrowText() {
  var h = roundAggregateHead;
  if (!h) return '▸';
  var body = h.parentNode.querySelector('.tool-agg-body');
  return body && body.style.display !== 'none' ? '▾' : '▸';
}

function updateToolResult(toolId, data) {
  // Find the first still-running entry for this tool name
  var allEntries = chatEl.querySelectorAll('.tool[data-tool="' + toolId + '"]');
  var div = null;
  for (var i = 0; i < allEntries.length; i++) {
    if (allEntries[i].getAttribute('data-state') === 'running') { div = allEntries[i]; break; }
  }
  if (!div) return;
  var dot = div.querySelector('.dot');
  var toggleEl = div.querySelector('.tool-toggle');
  var resultEl = div.querySelector('.tool-result');
  var error = data ? data.error || '' : '';
  var duration = data ? data.duration || 0 : 0;
  var resultText = data ? data.result_text || '' : '';
  var args = (data && data.arguments) ? data.arguments : {};
  var inlineDiff = data ? data.inline_diff || '' : '';

  // TICKET-DESK-V2D25：完成/失败瞬间移除流光 class（光停）
  div.classList.remove('shimmer');

  if (error) {
    dot.className = 'dot fail';
    div.setAttribute('data-state', 'failed');
    var timeElF = div.querySelector('.tool-time');
    if (timeElF) { timeElF.textContent = '—'; timeElF.classList.add('in'); }
    // 票 SAFETY-1：resultEl 空值守卫（与 1345 同源：DOM 结构异常时防 textContent 空引用）
    if (resultEl) { resultEl.className = 'tool-result error open'; resultEl.textContent = error.substring(0, 200); }
  } else {
    dot.className = 'dot done';
    div.setAttribute('data-state', 'done');
    // TICKET-DESK-V2B：耗时从状态文本迁出为独立时间列（.tool-time 44px 等宽右对齐）
    var timeEl = div.querySelector('.tool-time');
    if (timeEl) { timeEl.textContent = duration ? duration.toFixed(1) + 's' : '—'; timeEl.classList.add('in'); }
    // TICKET-D1d ①② + F3-5: 有 diff 时工具卡只留一行摘要，diff 本体搬出为独立区块
    if (resultText || Object.keys(args).length > 0) {
      resultEl.className = 'tool-result';
      div.setAttribute('data-result', resultText);
      if (inlineDiff) {
        // F3-5: 工具卡片只留一行摘要（"编辑文件 path +N/-M"），diff 区块独立于消息流
        // 票 SAFETY-1：resultEl/toggleEl 空值守卫（与 1345 同源防 textContent 空引用）
        if (resultEl) {
          resultEl.classList.add('open');
          resultEl.innerHTML = '<div class="tool-summary">' + esc(toolSummary(args, inlineDiff)) + '</div>';
        }
        if (toggleEl) toggleEl.textContent = '▾';
        appendDiffBlock(div, inlineDiff);
      } else {
        // 票 SAFETY-1：resultEl 空值守卫
        if (resultEl) resultEl.innerHTML = renderToolDetail(args, resultText, inlineDiff);
      }
    }
    // 票 SAFETY-1：toggleEl 空值守卫
    if (toggleEl) toggleEl.style.display = 'inline';
    if (!inlineDiff && toggleEl) toggleEl.textContent = '▸';
    // Notify when a tool > 2s completes
    if (duration > 2 && Notification.permission !== 'denied') {
      if (Notification.permission === 'granted') {
        new Notification('Bobo', { body: TOOL_FRIENDLY[toolId] || toolId + ' done (' + duration.toFixed(1) + 's)' });
      } else if (Notification.permission === 'default') {
        Notification.requestPermission();
      }
    }
  }
}
// TICKET-DESK-V2B2：上下文仪表盘 —— 进度药丸刷新 + 明细卡展开/收起
// TICKET-DESK-V2D5 修复（实弹断点）：call() 的 resolve 已是 result（pending 剥壳传 msg.result），
// 历史代码再取 res.result 二次剥壳 → d 恒 null → 药丸永停硬编码初值 0% · 0/128K
function refreshCtxStats() {
  call('context.stats', { session_id: currentSessionId || '' }).then(function(res) {
    var d = res || null;
    if (!d) return;
    // TICKET-DESK-V2D5：本轮记忆注入条数 = memory_injected（工作区累计值）回合内增量
    if (typeof d.memory_injected === 'number') {
      if (roundMemBaseline === null) { roundMemBaseline = d.memory_injected; roundMemInjected = 0; }
      else {
        roundMemInjected = d.memory_injected - roundMemBaseline;
        if (roundMemInjected < 0) { roundMemInjected = 0; roundMemBaseline = d.memory_injected; }
      }
    }
    // TICKET-DESK-V4: 药丸统计只读广播给小窗（投影数据源；不改主窗任何行为）
    // V4B: 带会话 sid（小窗按钉选过滤，药丸不跨会话串台）
    if (typeof window !== 'undefined' && window.boboAPI && window.boboAPI.widgetCtxStats) window.boboAPI.widgetCtxStats(d, currentSessionId);
    var fmt = function(n) { return (typeof n === 'number') ? String(n) : '—'; };
    // 药丸进度：百分比 = token 估算 / context_limit（context.stats 现返回上限，128K 兜底）
    var limit = (typeof d.context_limit === 'number' && d.context_limit > 0) ? d.context_limit : 128000;
    var used = (typeof d.token_estimate === 'number') ? d.token_estimate : 0;
    var pct = Math.min(100, Math.round(used * 100 / limit));
    var fill = document.getElementById('ctx-pill-fill');
    if (fill) fill.style.width = pct + '%';
    var pillText = document.getElementById('ctx-pill-text');
    if (pillText) {
      var kb = function(n) { return (n >= 1000) ? Math.round(n / 1000) + 'K' : String(n); };
      // TICKET-DESK-V2D5：认知状态条 —— 水位 + 本轮记忆注入 + 本轮工具调用（一条药丸，meta 弱化小字）
      var meta = '';
      if (roundMemInjected > 0) meta += ' <span class="v2d5-meta">· mem+' + roundMemInjected + '</span>';
      if (roundToolCount > 0) meta += ' <span class="v2d5-meta">· tools' + roundToolCount + '</span>';
      pillText.innerHTML = pct + '% · ' + kb(used) + '/' + kb(limit) + meta;
      // 三色阶墨痕化（色板派生零新色相）：<60% 文字墨痕 12% / ≥60% 品牌橙 15% / ≥85% 语义红 15%
      var color = pct >= 85 ? 'rgba(244,135,113,0.15)' : (pct >= 60 ? 'rgba(232,145,58,0.15)' : 'rgba(45,45,45,0.12)');
      if (fill) fill.style.background = color;
    }
    var det = document.getElementById('ctx-stats-detail');
    if (det) det.innerHTML =
      '<div class="ctx-row"><span>Context tokens (est.)</span><b>' + fmt(used) + '</b></div>' +
      '<div class="ctx-row"><span>Context limit</span><b>' + fmt(limit) + '</b></div>' +
      '<div class="ctx-row"><span>Chars saved</span><b>' + fmt(d.saved_chars) + '</b></div>' +
      '<div class="ctx-row"><span>Marked results</span><b>' + fmt(d.marked) + '</b></div>' +
      '<div class="ctx-row"><span>Memory injected</span><b>' + fmt(d.memory_injected) + '</b></div>' +
      '<div class="ctx-row"><span>Memory this round</span><b>' + roundMemInjected + '</b></div>' +
      '<div class="ctx-row"><span>Tools this round</span><b>' + roundToolCount + '</b></div>' +
      '<div class="ctx-note">Tokens estimated from current session messages; savings & injection are workspace cumulative; this-round values are per-turn increments.</div>';
  });
}
function toggleCtxStats() {
  var det = document.getElementById('ctx-stats-detail');
  if (!det) return;
  var open = det.style.display !== 'none';
  if (open) { det.style.display = 'none'; return; }
  det.style.display = 'block';
  refreshCtxStats(); // 展开时拉最新
}

// TICKET-D1d ②: diff 红绿高亮（+ 绿 / - 红 / @@ 蓝，兼容 ++/-- 文件头）
function diffHighlight(text) {
  var lines = esc(text).split('\n');
  for (var i = 0; i < lines.length; i++) {
    var l = lines[i];
    if (/^\+/.test(l) && !/^\+\+\+/.test(l)) lines[i] = '<span class="diff-add">' + l + '</span>';
    else if (/^-/.test(l) && !/^---/.test(l)) lines[i] = '<span class="diff-del">' + l + '</span>';
    else if (/^@@/.test(l)) lines[i] = '<span class="diff-file">' + l + '</span>';
  }
  return lines.join('\n');
}
// TICKET-GUI-F3 (F3-5): diff 行统计（+N/-M，排除 +++/--- 文件头）
function diffStats(text) {
  var add = 0, del = 0;
  if (!text) return { add: 0, del: 0 };
  text.split('\n').forEach(function(l) {
    if (/^\+/.test(l) && !/^\+\+\+/.test(l)) add++;
    else if (/^-/.test(l) && !/^---/.test(l)) del++;
  });
  return { add: add, del: del };
}
// TICKET-GUI-F3 (F3-5): 工具卡一行摘要 —— "编辑文件 path +N/-M"
function toolSummary(args, inlineDiff) {
  var pathKeys = ['file_path', 'path', 'filepath', 'filename', 'source', 'target'];
  var p = '';
  for (var i = 0; i < pathKeys.length; i++) {
    var v = args[pathKeys[i]];
    if (typeof v === 'string' && v) { p = v; break; }
  }
  var st = diffStats(inlineDiff);
  return (p ? p + ' ' : '') + '+' + st.add + '/-' + st.del;
}
// TICKET-GUI-F3 (F3-5): 独立 diff 区块（整行底色：绿=新增/红=删除/灰=上下文，@@ 文件头）
function diffBlock(text) {
  var lines = esc(text).split('\n');
  var html = '<div class="diff-block">';
  lines.forEach(function(l) {
    if (/^@@/.test(l)) html += '<div class="df">' + l + '</div>';
    else if (/^\+/.test(l) && !/^\+\+\+/.test(l)) html += '<div class="dl add">' + l + '</div>';
    else if (/^-/.test(l) && !/^---/.test(l)) html += '<div class="dl del">' + l + '</div>';
    else html += '<div class="dl ctx">' + (l ? l : '&nbsp;') + '</div>';
  });
  html += '</div>';
  return html;
}
// TICKET-GUI-F3 (F3-5): 在工具卡之后插入独立 diff 区块（与回复同级；聚合卡场景插到聚合卡后）
function appendDiffBlock(toolDiv, inlineDiff) {
  var block = document.createElement('div');
  block.innerHTML = diffBlock(inlineDiff);
  var child = block.firstChild;
  var aggBody = toolDiv.closest ? toolDiv.closest('.tool-agg-body') : null;
  var anchor = aggBody ? aggBody.parentNode : toolDiv;
  if (anchor.nextSibling) chatEl.insertBefore(child, anchor.nextSibling);
  else chatEl.appendChild(child);
}
// TICKET-D1d ① + F4-3: 工具卡片展开内容 = 路径 + 内容预览/diff + 结果（原始 JSON 永不直接上屏）
function renderToolDetail(args, resultText, inlineDiff) {
  var html = '';
  // F4-3: 禁倒原始 JSON —— 大字段（path/content 等）单独提取为"路径/预览"，
  // 绝不把整个 args JSON.stringify 糊屏
  var pathKeys = ['path', 'file_path', 'filepath', 'filename', 'source', 'target'];
  var contentKeys = ['content', 'new_string', 'old_string', 'text', 'note'];
  var hideKeys = { path:1, file_path:1, filepath:1, filename:1, source:1, target:1,
                   content:1, new_string:1, old_string:1, text:1, note:1 };
  var pv = null;
  for (var pi = 0; pi < pathKeys.length; pi++) {
    var v = args[pathKeys[pi]];
    if (typeof v === 'string' && v) { pv = { key: pathKeys[pi], val: v }; break; }
  }
  if (pv) {
    html += '<span class="td-args">Path</span>\n' + esc(pv.val) + '\n';
  }
  // F4-3: 内容字段全部展示（edit_file 的原文/新文、write 的 content），每个独立截断预览
  for (var ci = 0; ci < contentKeys.length; ci++) {
    var cvv = args[contentKeys[ci]];
    if (typeof cvv !== 'string' || !cvv) continue;
    var previewLabel = contentKeys[ci] === 'old_string' ? 'Original' : contentKeys[ci] === 'new_string' ? 'New' : 'Content';
    var previewText = cvv;
    if (previewText.length > 300) previewText = previewText.substring(0, 300) + '\n... (preview truncated, ' + cvv.length + ' chars)';
    html += '<span class="td-args">' + previewLabel + '</span>\n' + esc(previewText) + '\n';
  }
  // 其余小参数（action/recursive 等）若总量小仍显示，超限则省略（防倾泻）
  var extra = {};
  Object.keys(args).forEach(function(k) { if (!hideKeys[k]) extra[k] = args[k]; });
  var extraJson = JSON.stringify(extra, null, 2);
  if (Object.keys(extra).length > 0 && extraJson.length < 300) {
    html += '<span class="td-args">Args</span>\n' + esc(extraJson) + '\n';
  }
  if (resultText) {
    if (html) html += '\n';
    html += '<span class="td-args">Result</span>\n' + diffHighlight(resultText) + '\n';
  }
  if (inlineDiff) {
    html += '<div class="inline-diff">' + diffHighlight(inlineDiff) + '</div>';
  }
  return html || '(no output)';
}
function addStatus(text) {
  var div = document.createElement('div'); div.className = 'status'; div.textContent = text;
  chatEl.appendChild(div); chatEl.scrollTop = chatEl.scrollHeight;
}
