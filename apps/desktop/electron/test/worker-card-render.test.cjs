// worker-card-render.test.cjs — TICKET-DESK-WORKER-VISIBLE worker 折叠卡专项测试
// 被测对象：dist/index.html 内真实 worker 卡函数（从 HTML 抽取源码执行，不复制逻辑）
// 验证四条不变量：事件判别 / 独立折叠卡创建 / 单步收工 dot 转 done / 收工收纳进主卡
'use strict'
const test = require('node:test')
const assert = require('node:assert')
const fs = require('fs')
const path = require('path')
const vm = require('vm')

const ROOT = path.resolve(__dirname, '..', '..', '..', '..')
const INDEX_HTML = path.join(ROOT, 'apps', 'desktop', 'dist', 'index.html')

// 从 dist/index.html 抽取真实函数源码（括号配对定位函数体，测真代码）
function grabFn(html, name) {
  const start = html.indexOf('function ' + name)
  assert.ok(start >= 0, 'function ' + name + ' not found in index.html')
  let i = html.indexOf('{', start)
  let depth = 0
  for (; i < html.length; i++) {
    if (html[i] === '{') depth++
    else if (html[i] === '}') { depth--; if (depth === 0) break }
  }
  return html.slice(start, i + 1)
}

// 最小 DOM 桩：覆盖 worker 卡函数用到的元素能力（createElement/appendChild/className/
// classList/attrs/querySelector/querySelectorAll + 内嵌 HTML 的最小 span/svg 解析）
function FakeEl(tag) {
  const el = {
    tagName: tag, className: '', attrs: {}, children: [], parentNode: null,
    style: {}, textContent: '', onclick: null, scrollTop: 0,
    classList: {
      add(c) { if (!el.classList.contains(c)) el.className = (el.className ? el.className + ' ' : '') + c; },
      remove(c) { el.className = el.className.split(/\s+/).filter((x) => x !== c).join(' '); },
      contains(c) { return el.className.split(/\s+/).indexOf(c) !== -1; },
    },
    setAttribute(k, v) { el.attrs[k] = String(v); },
    getAttribute(k) { return k in el.attrs ? el.attrs[k] : null; },
    appendChild(c) { el.children.push(c); c.parentNode = el; return c; },
    querySelector(sel) { return findAll(el, sel)[0] || null; },
    querySelectorAll(sel) { return findAll(el, sel); },
  }
  Object.defineProperty(el, 'innerHTML', {
    set(v) {
      el.children = []
      // 只解析本功能用到的形态：<span class="X">文本</span> 与 <svg ...>…</svg>（opaque）
      const re = /<span class="([^"]*)">([^<]*)<\/span>|<svg[^>]*>.*?<\/svg>/g
      let m
      while ((m = re.exec(v))) {
        const isSvg = m[0].startsWith('<svg')
        const kid = FakeEl(isSvg ? 'svg' : 'span')
        if (!isSvg) { kid.className = m[1]; kid.textContent = m[2]; }
        el.children.push(kid); kid.parentNode = el
      }
    },
    get() { return '' },
  })
  return el
}
function findAll(root, sel) {
  // 支持 '.cls' 与 '.cls[data-wrow="..."]'（worker 卡用到的两种选择器）
  const m = sel.match(/^\.([\w-]+)(?:\[data-wrow="([^"]*)"\])?$/)
  const out = []
  ;(function walk(node) {
    node.children.forEach((c) => {
      if (m && c.className.split(/\s+/).indexOf(m[1]) !== -1) {
        if (!m[2] || c.attrs['data-wrow'] === m[2]) out.push(c)
      }
      walk(c)
    })
  })(root)
  return out
}

function loadWorkerFns() {
  const html = fs.readFileSync(INDEX_HTML, 'utf8')
  const names = ['esc', 'isWorkerEvent', 'setupWorkerMainCard', 'ensureWorkerCard',
                 'renderWorkerToolStart', 'renderWorkerToolComplete',
                 'renderWorkerPhase', 'foldWorkerIntoMain']
  const src = names.map((n) => grabFn(html, n)).join('\n')
  const chatEl = FakeEl('div')
  const ctx = {
    console, chatEl,
    document: { createElement: (t) => FakeEl(t) },
    TOOL_FRIENDLY: {}, TOOL_ICONS: {}, toolIcon: () => '',
    workerMainCards: {}, workerCards: {},
  }
  vm.createContext(ctx)
  vm.runInContext(src, ctx)
  return ctx
}

test('worker 事件判别：spawn 主卡非 worker 事件，内部事件是', () => {
  const c = loadWorkerFns()
  assert.strictEqual(c.isWorkerEvent({ name: 'spawn_worker', worker: 'explorer-1' }), false)
  assert.strictEqual(c.isWorkerEvent({ name: 'grep_code', worker: 'explorer-1' }), true)
  assert.strictEqual(c.isWorkerEvent({ worker: 'explorer-1', message: '正在思考...' }), true)
  assert.strictEqual(c.isWorkerEvent({ name: 'read_local_file' }), false)
})

test('主卡挂收纳位并登记配对', () => {
  const c = loadWorkerFns()
  const main = FakeEl('div')
  c.setupWorkerMainCard(main, 'explorer-1')
  assert.strictEqual(main.getAttribute('data-worker'), 'explorer-1')
  assert.strictEqual(main.querySelector('.worker-slot') !== null, true)
  assert.strictEqual(c.workerMainCards['explorer-1'], main)
})

test('worker 事件建独立折叠卡，工具行/阶段进卡', () => {
  const c = loadWorkerFns()
  c.renderWorkerToolStart({ name: 'grep_code', worker: 'explorer-1', role: 'explorer', context: 'config', tool_id: 'w-explorer-1-grep_code' })
  c.renderWorkerPhase({ worker: 'explorer-1', role: 'explorer', message: '正在思考...' })
  const card = c.workerCards['explorer-1']
  assert.ok(card, '应创建独立折叠卡')
  assert.strictEqual(card.className, 'worker-card')
  assert.strictEqual(card.parentNode, c.chatEl, '折叠卡应在消息流中（独立于主卡）')
  const rows = card.querySelectorAll('.worker-row[data-wrow="w-explorer-1-grep_code"]')
  assert.strictEqual(rows.length, 1, '工具调用应建一行')
  const ph = card.querySelector('.worker-phase')
  assert.ok(ph && ph.textContent.indexOf('正在思考') !== -1, '阶段应写入卡头')
})

test('单步收工：行内 dot 转 done + 耗时', () => {
  const c = loadWorkerFns()
  c.renderWorkerToolStart({ name: 'grep_code', worker: 'explorer-1', role: 'explorer', context: 'config', tool_id: 'w-explorer-1-grep_code' })
  c.renderWorkerToolComplete({ name: 'grep_code', worker: 'explorer-1', role: 'explorer', tool_id: 'w-explorer-1-grep_code', duration: 1.5, success: true })
  const card = c.workerCards['explorer-1']
  const rows = card.querySelectorAll('.worker-row[data-wrow="w-explorer-1-grep_code"]')
  const dot = rows[0].querySelector('.dot')
  assert.ok(dot && dot.className.indexOf('done') !== -1, 'dot 应转 done')
  const tm = rows[0].querySelector('.worker-row-time')
  assert.strictEqual(tm.textContent, '1.5s')
})

test('收工收纳：独立折叠卡移入主卡 .worker-slot，登记清空', () => {
  const c = loadWorkerFns()
  const main = FakeEl('div')
  c.setupWorkerMainCard(main, 'explorer-1')
  c.renderWorkerToolStart({ name: 'grep_code', worker: 'explorer-1', role: 'explorer', context: 'config', tool_id: 'w-explorer-1-grep_code' })
  const wc = c.workerCards['explorer-1']
  c.foldWorkerIntoMain('explorer-1')
  const slot = main.querySelector('.worker-slot')
  assert.strictEqual(slot.children.indexOf(wc) !== -1, true, '折叠卡应移入主卡收纳位')
  assert.strictEqual(c.workerMainCards['explorer-1'], null, '收纳后清登记')
  assert.strictEqual(c.workerCards['explorer-1'], null, '收纳后清折叠卡登记')
})
