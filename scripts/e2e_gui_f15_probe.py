"""票 GUI-F15 实弹验收：Playwright CDP 连真实 Electron（复用 V2D5 e2e_pill_probe 方案）。

验收四项（票面强制）：
  ① 页面加载后 #plugin-list .pitem = 4 项
  ② 四项逐一点击，右侧 right-panel 每次 open 且内容非空
  ③ 四个图标全是 <svg>（无 emoji）
  ④ 控制台零错误（console.error / pageerror）

截图落盘：data/eval/gui_f15_probe.png
用法：.venv/bin/python scripts/e2e_gui_f15_probe.py
"""

import json
import re
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path("/Users/niuqingwei/Desktop/boboagent_main")
MAIN_CJS = REPO / "apps" / "desktop" / "electron" / "main.cjs"
ELECTRON_BIN = REPO / "apps" / "desktop" / "node_modules" / ".bin" / "electron"
CDP_PORT = 9334
SHOT = REPO / "data" / "eval" / "gui_f15_probe.png"

EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]")

JS_ICONS = """
() => Array.from(document.querySelectorAll('#plugin-list .pitem')).map(p => ({
  pid: p.dataset.pid,
  iconHtml: p.querySelector('.pi-icon') ? p.querySelector('.pi-icon').innerHTML : '',
}))
"""

JS_PANEL_STATE = """
() => {
  const panel = document.getElementById('right-panel');
  const content = document.getElementById('right-content');
  return {
    open: panel ? panel.classList.contains('open') : false,
    contentLen: content ? content.innerHTML.trim().length : -1,
  };
}
"""


def main():
    print("[1] spawn electron (CDP :%d) ..." % CDP_PORT, flush=True)
    proc = subprocess.Popen(
        [str(ELECTRON_BIN), str(MAIN_CJS), f"--remote-debugging-port={CDP_PORT}"],
        cwd=str(REPO),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    errors = []
    fail = []

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
                print("[2] CDP connect FAILED", flush=True)
                return 1

            win = None
            for _ in range(30):
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
                print("[2] main window not found", flush=True)
                return 1

            # 挂错误监听（从此刻起收集；页面若已加载成功，④ 判定以"渲染成功后零新错"为准）
            win.on("console", lambda m: errors.append(
                f"console.{m.type}: {m.text}") if m.type == "error" else None)
            win.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))

            win.wait_for_load_state("domcontentloaded", timeout=60000)
            win.wait_for_selector("#plugin-list .pitem", timeout=60000)
            print("[2] window loaded, plugin-list rendered", flush=True)

            # 等后端连接就绪（telescope 面板需要真实数据）
            ready = False
            deadline = time.time() + 45
            st = {}
            while time.time() < deadline:
                try:
                    st = win.evaluate("() => ({ connected, currentSessionId })")
                    if st.get("connected") and st.get("currentSessionId"):
                        ready = True
                        break
                except Exception:
                    pass
                time.sleep(1)
            print(f"[3] backend ready={ready} state={json.dumps(st, ensure_ascii=False)}", flush=True)

            # ── ① pitem 数量 = 4 ──
            pitems = win.query_selector_all("#plugin-list .pitem")
            n = len(pitems)
            print(f"[4] #plugin-list .pitem count = {n}", flush=True)
            if n != 4:
                fail.append(f"① pitem 应为 4，实际 {n}")

            # ── ③ 图标全 <svg> 无 emoji ──
            icons = win.evaluate(JS_ICONS)
            print(f"[5] icons = {json.dumps(icons, ensure_ascii=False)}", flush=True)
            for it in icons:
                h = it["iconHtml"]
                if "<svg" not in h:
                    fail.append(f"③ {it['pid']} 图标非 SVG: {h[:80]}")
                if EMOJI_RE.search(h):
                    fail.append(f"③ {it['pid']} 图标含 emoji: {h[:80]}")

            # ── ② 四项逐一点击 ──
            print("[6] click each plugin ...", flush=True)
            for pid in ("notes", "project", "terminal", "telescope"):
                clicked = win.evaluate(
                    "(sel) => { const el = document.querySelector(sel);"
                    " if (!el) return false; el.click(); return true; }",
                    f'#plugin-list .pitem[data-pid="{pid}"]',
                )
                if not clicked:
                    fail.append(f"② {pid} 未找到 pitem 节点")
                    continue
                # 等面板打开且内容非空（最多 5s，telescope 需等后端应答）
                ok = False
                stp = {}
                for _ in range(25):
                    time.sleep(0.2)
                    stp = win.evaluate(JS_PANEL_STATE)
                    if stp["open"] and stp["contentLen"] > 0:
                        ok = True
                        break
                print(f"    {pid}: open={stp.get('open')} contentLen={stp.get('contentLen')}", flush=True)
                if not ok:
                    fail.append(f"② {pid} 点击后面板未正常打开/内容空: {json.dumps(stp)}")
                # 关面板再点下一项（closePanel 由页面内 ✕ 触发，直接 evaluate 调）
                win.evaluate("document.getElementById('right-panel').classList.remove('open')")

            # 截图
            SHOT.parent.mkdir(parents=True, exist_ok=True)
            win.screenshot(path=str(SHOT))
            print(f"[7] screenshot -> {SHOT}", flush=True)

            # ── ④ 控制台零错误 ──
            print(f"[8] console/page errors = {json.dumps(errors, ensure_ascii=False)}", flush=True)
            if errors:
                fail.append(f"④ 控制台错误: {errors}")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    print("=" * 50, flush=True)
    if fail:
        print("GUI-F15 E2E FAIL:", flush=True)
        for f in fail:
            print("  -", f, flush=True)
        return 1
    print("GUI-F15 E2E PASS (①4项 ②四击全开 ③全SVG ④零错误)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
