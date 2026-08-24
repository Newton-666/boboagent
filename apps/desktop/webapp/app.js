/on* 事件/iframe 等一律清除）
      out = window.DOMPurify.sanitize(out, { USE_PROFILES: { html: true } });
    } else {
      // vendor 未就绪（理论不发生：本地引入）：回退既有简渲染
      out = md(s);
    }
    // TICKET-GUI-F16：数学公式还原（KaTeX 渲染；降级/失败原样文本，绝不 throw）
    out = restoreMath(out, mathPack.placeholders);
    if (handoffCard) { out = out.replace(/%%HANDOFF_CARD%%/g, handoffCard.card); }
    if (worktreeCard) { out = out.replace(/%%WORKTREE_CARD%%/g, worktreeCard.card); }
    return out;
  } catch (e) {
    // 兜底：任何异常不回退页面 —— 先试既有管线，再退纯文本转义
    try { return md(s); } catch (e2) { return esc(s); }
  }
}

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
on('tool.start', function(data) {
  if (isForeignSession(data)) return;
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
  addTool(data ? data.name || data.tool_id || 'Tool' : 'Tool',
          data ? data.context || '' : '',
          data ? data.tool_id || 't'+Date.now() : 't'+Date.now());
});
on('tool.complete', function(data) {
  if (isForeignSession(data)) return;
  var tid = data ? data.tool_id || '' : '';
  if (tid) updateToolResult(tid, data);
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
