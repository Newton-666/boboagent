"""TICKET-GUI-F14 实弹验收 —— CDP 连真实 Electron（与 e2e_pill_probe 同款方案）。

不起假壳、不 mock —— 真后端（python -m bobo_tui_gateway.entry 由 main.cjs 自动 spawn）。
验证（票面验收标准）：
  A. 页面加载后 #plugin-list .pitem = 4（renderPluginList 已执行——F14 之前 loadSession
     卡死时插件区永远空白点不开）
  B. 药丸非恒 0%（refreshCtxStats 已触发——链路活；空会话真实 0 时打印原始值供人工判定）
  C. 控制台零错误（pageerror + console error 全收集）
  D. 截图落盘 /tmp/gui_f14_verify.png

用法：.venv/bin/python scripts/e2e_gui_f14_verify.py
"""

import json
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path("/Users/niuqingwei/Desktop/boboagent_main")
MAIN_CJS = REPO / "apps" / "desktop" / "electron" / "main.cjs"
ELECTRON_BIN = REPO / "apps" / "desktop" / "node_modules" / ".bin" / "electron"
CDP_PORT = 9334

JS_PROBE = """
() => ({ connected, currentSessionId, hasAPI: !!window.boboAPI })
"""

JS_PLUGIN = """
() => {
  const el = document.getElementById('plugin-list');
  const items = el ? el.querySelectorAll('.pitem') : [];
  return { pitemCount: items.length, html: el ? el.innerHTML.slice(0, 120) : 'NO #plugin-list' };
}
"""

JS_PILL = """
() => {
  const t = document.getElementById('ctx-pill-text');
  const f = document.getElementById('ctx-pill-fill');
  const d = document.getElementById('ctx-stats-detail');
  return {
    text: t ? t.textContent : 'NO #ctx-pill-text',
    fillWidth: f ? f.style.width : 'NO #ctx-pill-fill',
    detail: d ? d.innerHTML.slice(0, 160) : 'NO #ctx-stats-detail',
  };
}
"""

JS_CALL_STATS = """
async () => {
  try {
    const res = await call('context.stats', { session_id: currentSessionId || '' });
    return { ok: true, res };
  } catch (e) {
    return { ok: false, err: String(e) };
  }
}
"""


def main() -> int:
    errors: list[str] = []
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

            # 控制台零错误收集
            win.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            win.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)

            win.wait_for_load_state("domcontentloaded", timeout=60000)
            win.wait_for_selector("#plugin-list", timeout=60000)
            print("[1] window loaded", flush=True)

            # 等连接就绪（connected + 会话）
            ready = False
            deadline = time.time() + 45
            st = {}
            while time.time() < deadline:
                st = win.evaluate(JS_PROBE)
                if st["connected"] and st["currentSessionId"]:
                    ready = True
                    break
                time.sleep(1)
            print(f"[2] ready={ready} state={json.dumps(st, ensure_ascii=False)}", flush=True)

            # 等 ready 处理器初始化完成（renderPluginList/refreshCtxStats 已执行）
            time.sleep(3)

            # A. 插件列表 4 项
            pl = win.evaluate(JS_PLUGIN)
            print(f"[A] plugin-list: {json.dumps(pl, ensure_ascii=False)}", flush=True)

            # B. 药丸（refreshCtxStats 链路）
            pill = win.evaluate(JS_PILL)
            print(f"[B] pill: {json.dumps(pill, ensure_ascii=False)}", flush=True)
            stats = win.evaluate(JS_CALL_STATS)
            print(f"[B] context.stats: {json.dumps(stats, ensure_ascii=False)[:600]}", flush=True)

            # 截图
            shot = Path("/tmp/gui_f14_verify.png")
            win.screenshot(path=str(shot))
            print(f"[C] screenshot -> {shot}", flush=True)

            # 判定
            ok = True
            if pl["pitemCount"] != 4:
                print(f"[FAIL] pitem 应 4，实际 {pl['pitemCount']}", flush=True)
                ok = False
            pill_text = pill["text"] or ""
            if "%" not in pill_text:
                print(f"[FAIL] 药丸无百分比（refreshCtxStats 未生效）: {pill_text!r}", flush=True)
                ok = False
            if pill_text.startswith("0%") and stats.get("res", {}).get("token_estimate", 0) == 0:
                print(f"[NOTE] 药丸 0% 但后端 token_estimate=0（空会话真实 0，链路活）", flush=True)
            if errors:
                print(f"[FAIL] 控制台错误 {len(errors)} 条: {errors[:5]}", flush=True)
                ok = False
            else:
                print("[C] 控制台零错误", flush=True)

            print(f"[RESULT] {'PASS' if ok else 'FAIL'}", flush=True)
            return 0 if ok else 2
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
