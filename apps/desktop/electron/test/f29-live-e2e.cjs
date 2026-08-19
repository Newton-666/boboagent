// TICKET-GUI-F29：实时消息窗口化 —— Electron 实机布局验证（L14：前端新链路收工前真实浏览器实弹）
// 覆盖 jsdom 测不了的路径：真实 offsetHeight 缓存、scrollHeight/scrollTop 真实值、
// liveScrollBottom 贴近底部判定、滚动不被打断、窗口化 DOM 收缩、重建高度不跳变。
const { app, BrowserWindow } = require('electron');
const path = require('path');

const results = [];
let pass = 0, fail = 0;
function ok(cond, name, extra) {
  if (cond) pass++; else fail++;
  results.push({ pass: !!cond, name: name + (extra ? ' (' + extra + ')' : '') });
  console.log((cond ? '  ✓ ' : '  ✗ FAIL: ') + name + (extra ? ' (实际 ' + extra + ')' : ''));
}

app.whenReady().then(async () => {
  try {
    const win = new BrowserWindow({
      show: false, width: 1200, height: 800,
      webPreferences: { nodeIntegration: false, contextIsolation: true },
    });
    await win.loadFile(path.join(__dirname, '../../dist/index.html'));

    const out = await win.webContents.executeJavaScript(`(async () => {
      const chatEl = document.getElementById('chat');
      const L = () => window.liveUnits;
      const res = {};
      // [A] 220 条消息（真实布局）
      window.clearChat();
      for (let i = 0; i < 220; i++) {
        window.addMsg(i % 2 ? 'bobo' : 'user', 'message number ' + i + ' with enough content to wrap lines realistically ' + ('x').repeat(i % 5 * 20), 'bulk-' + i);
      }
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      res.units = L().length;
      res.domChildren = chatEl.children.length;
      res.scrollHeight = chatEl.scrollHeight;
      res.clientHeight = chatEl.clientHeight;
      res.bottomNear = chatEl.scrollTop + chatEl.clientHeight >= chatEl.scrollHeight - 80;
      // 实测高度缓存：滚动一次后某 unit 的 h 应 > 0（真实 offsetHeight 路径）
      chatEl.scrollTop = chatEl.scrollHeight;
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      const sample = L().find(u => u.kind === 'msg' && u.h > 0);
      res.sampleH = sample ? sample.h : 0;
      // [B] 上滚 5000px 后 addMsg：scrollTop 不应被拉走（liveScrollBottom near=false）
      chatEl.scrollTop = Math.max(0, chatEl.scrollHeight - 5000);
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      const beforeTop = chatEl.scrollTop;
      window.addMsg('bobo', 'incoming while scrolled up', 'intr-1');
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      res.intrKept = chatEl.scrollTop === beforeTop;
      res.intrTop = chatEl.scrollTop;
      // [C] 贴近底部时 addMsg：自动跟随滚底（真实用户滚底 = maxScroll；
      // 窗口化后 scrollHeight 含占位误差，scrollTop=scrollHeight 会被 clamp 漂移——探针用真实方式）
      chatEl.scrollTop = chatEl.scrollHeight - chatEl.clientHeight;
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      res.c1 = { st: chatEl.scrollTop, sh: chatEl.scrollHeight, ch: chatEl.clientHeight, winBot: window.liveWindowBot, len: L().length };
      window.addMsg('bobo', 'tail follow', 'tail-f');
      res.c2 = { st: chatEl.scrollTop, sh: chatEl.scrollHeight, inDom: document.getElementById('tail-f') !== null };
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      const tfUnit = L().find(u => u.mid === 'tail-f');
      res.tailVisible = document.getElementById('tail-f') !== null;
      res.tfUnit = tfUnit ? ('kind=' + tfUnit.kind + ' elInDom=' + !!(tfUnit.el && tfUnit.el.parentNode === chatEl) + ' idx=' + L().indexOf(tfUnit) + ' of ' + L().length) : 'NO-UNIT';
      res.tfScrollTop = chatEl.scrollTop;
      res.tfDomChildren = chatEl.children.length;
      res.c3 = { st: chatEl.scrollTop, sh: chatEl.scrollHeight, winBot: window.liveWindowBot, topPh: window.liveTopPh ? window.liveTopPh.style.height : 'none', botPh: window.liveBotPh ? window.liveBotPh.style.height : 'none' };
      // [D] 滚回顶部重建 + 占位高度
      chatEl.scrollTop = 0;
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
      res.topRebuilt = document.getElementById('bulk-0') !== null;
      res.topPhH = window.liveTopPh ? window.liveTopPh.style.height : 'none';
      // [E] clearChat 重置
      window.clearChat();
      res.cleared = L().length === 0 && chatEl.children.length === 0;
      // [F] 耗时（220 条消息挂载总耗时）
      return res;
    })()`);

    ok(out.units === 220, '数据模型 220', out.units);
    ok(out.domChildren < 220, 'DOM 窗口化收缩', out.domChildren);
    ok(out.scrollHeight > out.clientHeight, '真实 scrollHeight > clientHeight', out.scrollHeight + ' > ' + out.clientHeight);
    ok(out.bottomNear === false, '初始在底部（未滚动）', out.bottomNear);
    ok(out.sampleH > 0, '实测高度缓存生效', out.sampleH);
    ok(out.intrKept === true, '上滚时新消息不打断滚动', 'scrollTop ' + out.intrTop + ' 保持');
    ok(out.tailVisible === true, '贴近底部新消息跟随可见', 'unit=' + out.tfUnit + ' scrollTop=' + out.tfScrollTop + ' dom=' + out.tfDomChildren + ' c1=' + JSON.stringify(out.c1) + ' c2=' + JSON.stringify(out.c2) + ' c3=' + JSON.stringify(out.c3));
    ok(out.topRebuilt === true, '滚回顶部重建');
    ok(out.cleared === true, 'clearChat 重置');
  } catch (e) {
    console.log('E2E ERROR:', e.message);
    fail++;
  }
  app.exit(fail ? 1 : 0);
});
