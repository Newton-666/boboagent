"""DIAG-1 实战验收 —— 药丸不动实弹复现探针（修复前取证 / 修复后验证共用）。

票 COST-3 归档：原为 /tmp/probe_pill_repro.py（DIAG-1 临时探针），2026-08-16
收编进 scripts/ 长期保留；CDP 端口可用参数传入（默认 9336），用法同 DIAG-1。

连真实 Electron（CDP），发一条 prompt.submit，对比：
- 发消息前后 #ctx-pill-text 文本（DOM 里药丸显示）
- 发消息前后 context.stats 的 token_estimate（后端真实值）
症状判定：token_estimate 变化而药丸文本不变 = 药丸不更新（复现成功）。
"""

import json
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path("/Users/niuqingwei/Desktop/boboagent_main")
MAIN_CJS = REPO / "apps" / "desktop" / "electron" / "main.cjs"
ELECTRON_BIN = REPO / "apps" / "desktop" / "node_modules" / ".bin" / "electron"
CDP_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9336

JS_PROBE = """
() => {
  const t = document.getElementById('ctx-pill-text');
  const txt = document.getElementById('ctx-pill-txt');
  const det = document.getElementById('ctx-stats-detail');
  return {
    pillText: t ? t.textContent : 'NO #ctx-pill-text',
    pillTxtExists: !!txt,
    fillWidth: (function(){ const f = document.getElementById('ctx-pill-fill'); return f ? f.style.width : 'NO #ctx-pill-fill'; })(),
    detail: det ? det.innerHTML.slice(0, 200) : 'NO #ctx-stats-detail',
    connected: typeof window !== 'undefined' && !!window.boboAPI,
    currentSessionId: (typeof currentSessionId !== 'undefined') ? currentSessionId : null,
  };
}
"""

JS_STATS = """
async () => {
  try {
    const res = await call('context.stats', { session_id: currentSessionId || '' });
    return { ok: true, token_estimate: res.token_estimate, context_limit: res.context_limit };
  } catch (e) {
    return { ok: false, err: String(e) };
  }
}
"""

JS_SEND_PROMPT = """
(text) => {
  if (window.boboAPI && window.boboAPI.send) {
    window.boboAPI.send({
      jsonrpc: '2.0', id: 'probe-prompt', method: 'prompt.submit',
      params: { session_id: currentSessionId || '', text: text },
    });
    return 'sent';
  }
  return 'NO boboAPI.send';
}
"""


def main() -> int:
    proc = subprocess.Popen(
        [str(ELECTRON_BIN), str(MAIN_CJS), f"--remote-debugging-port={CDP_PORT}"],
        cwd=str(REPO),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        with sync_playwright() as p:
            browser = None
            deadline = time.time() + 60
            while time.time() < deadline:
                try:
                    browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
                    break
                except Exception:
                    time.sleep(1.5)
            if not browser:
                print("[FAIL] CDP connect", flush=True)
                return 1

            win = None
            for _ in range(20):
                for ctx in browser.contexts:
                    for pg in ctx.pages:
                        if "index.html" in pg.url or "dist" in pg.url:
                            win = pg
                            break
                    if win:
                        break
                if win:
                    break
                time.sleep(1.5)
            if not win:
                print("[FAIL] main window not found", flush=True)
                return 1

            win.wait_for_load_state("domcontentloaded", timeout=60000)
            win.wait_for_selector("#ctx-pill-text", timeout=60000)

            # 等连接就绪（boboAPI + 会话），轮询打点
            ready = False
            deadline = time.time() + 90
            probe = {}
            tick = 0
            while time.time() < deadline:
                probe = win.evaluate(JS_PROBE)
                if probe["connected"] and probe["currentSessionId"]:
                    ready = True
                    break
                tick += 1
                if tick % 10 == 0:
                    print(f"[wait-{tick * 3}s] {json.dumps(probe, ensure_ascii=False)}", flush=True)
                time.sleep(3)
            print(f"[ready] ready={ready} probe={json.dumps(probe, ensure_ascii=False)}", flush=True)

            # 基线取证
            st0 = win.evaluate(JS_STATS)
            print(f"[BASE] pillText={probe['pillText']!r} pillTxtExists={probe['pillTxtExists']} "
                  f"fillWidth={probe['fillWidth']!r} stats={json.dumps(st0, ensure_ascii=False)}", flush=True)

            # 发一条消息触发回合（token 应变化）
            r = win.evaluate(JS_SEND_PROMPT, "你好，这是一条 DIAG-1 实弹验收测试消息")
            print(f"[SEND] {r}", flush=True)

            # 等后端处理 + 回合结束触发 refreshCtxStats（dist:2949）
            time.sleep(15)

            # 修复前/后对比取证
            probe2 = win.evaluate(JS_PROBE)
            st1 = win.evaluate(JS_STATS)
            print(f"[AFTER] pillText={probe2['pillText']!r} pillTxtExists={probe2['pillTxtExists']} "
                  f"fillWidth={probe2['fillWidth']!r} stats={json.dumps(st1, ensure_ascii=False)}", flush=True)

            shot = Path("/tmp/pill_repro.png")
            win.screenshot(path=str(shot))
            print(f"[SHOT] -> {shot}", flush=True)

            # 判定：token 变化 vs 药丸文本变化
            tok0 = st0.get("token_estimate") if st0.get("ok") else None
            tok1 = st1.get("token_estimate") if st1.get("ok") else None
            text0 = probe["pillText"]
            text1 = probe2["pillText"]
            print(f"[VERDICT] token: {tok0} -> {tok1} | pillText: {text0!r} -> {text1!r}", flush=True)
            if tok0 != tok1 and text0 == text1:
                print("[RESULT] SYMPTOM-REPRODUCED 药丸文本未随 token 变化", flush=True)
                return 3
            if text0 != text1:
                print("[RESULT] PILL-UPDATED 药丸文本已随回合更新", flush=True)
                return 0
            print("[RESULT] NO-CHANGE 两侧都没变（消息可能未处理，需人工判定）", flush=True)
            return 4
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
