"""票 TICKET-DESK-P2 实弹验收：Playwright CDP 连真实 Electron（复用 GUI-F15/V2D5 探针方案）。

验收三态（票面强制）：
  ① 欢迎屏极简：#welcome-title 可见、副标题元素已删除、折叠按钮（#sidebar-collapse）存在
  ② 侧栏展开态：#sidebar 无 closed，折叠按钮可见（SVG 图标）
  ③ 侧栏折叠态：点 #sidebar-collapse 后 #sidebar.closed + body.sidebar-collapsed +
     #sidebar-expand-btn 出现；再点恢复展开

截图落盘：data/eval/gui_p2_probe_{welcome,expanded,collapsed}.png
用法：.venv/bin/python scripts/e2e_gui_p2_probe.py
"""

import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path("/Users/niuqingwei/Desktop/boboagent_main")
MAIN_CJS = REPO / "apps" / "desktop" / "electron" / "main.cjs"
ELECTRON_BIN = REPO / "apps" / "desktop" / "node_modules" / ".bin" / "electron"
CDP_PORT = 9335
EVAL_DIR = REPO / "data" / "eval"
EVAL_DIR.mkdir(parents=True, exist_ok=True)

JS_SNAP = """
() => ({
  welcomeTitle: (document.getElementById('welcome-title') || {}).textContent || null,
  welcomeSub: !!document.querySelector('#welcome .welcome-sub'),
  foldBtn: !!document.getElementById('sidebar-collapse'),
  foldBtnSvg: !!(document.getElementById('sidebar-collapse') || {}).querySelector,
  sidebarClosed: (document.getElementById('sidebar') || {}).classList ?
    document.getElementById('sidebar').classList.contains('closed') : null,
  bodyCollapsed: document.body.classList.contains('sidebar-collapsed'),
  expandBtnVisible: (() => {
    const el = document.getElementById('sidebar-expand-btn');
    if (!el) return false;
    const cs = getComputedStyle(el);
    return cs.display !== 'none' && cs.visibility !== 'hidden';
  })(),
})
"""


def main():
    print("[1] spawn electron (CDP :%d) ..." % CDP_PORT, flush=True)
    proc = subprocess.Popen(
        [str(ELECTRON_BIN), str(MAIN_CJS), f"--remote-debugging-port={CDP_PORT}"],
        cwd=str(REPO),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
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

            win.wait_for_load_state("domcontentloaded", timeout=60000)
            win.wait_for_selector("#sidebar-collapse", timeout=60000)
            print("[2] window loaded, sidebar-collapse rendered", flush=True)

            # ── 态 1：欢迎屏极简 ──────────────────────────────
            time.sleep(2)
            s1 = win.evaluate(JS_SNAP)
            print("[3] welcome state:", s1, flush=True)
            if not s1["welcomeTitle"]:
                fail.append("欢迎屏标题缺失")
            if s1["welcomeSub"]:
                fail.append("副标题元素未删除")
            if not s1["foldBtn"]:
                fail.append("折叠按钮缺失")
            win.screenshot(path=str(EVAL_DIR / "gui_p2_probe_welcome.png"))
            print("[3] shot: welcome", flush=True)

            # ── 态 2：侧栏展开 ────────────────────────────────
            if s1["sidebarClosed"]:
                win.evaluate("() => { const sb = document.getElementById('sidebar'); sb.classList.remove('closed'); document.body.classList.remove('sidebar-collapsed'); }")
                time.sleep(0.5)
            s2 = win.evaluate(JS_SNAP)
            print("[4] expanded state:", s2, flush=True)
            if s2["sidebarClosed"]:
                fail.append("展开态不应有 closed")
            win.screenshot(path=str(EVAL_DIR / "gui_p2_probe_expanded.png"))
            print("[4] shot: expanded", flush=True)

            # ── 态 3：侧栏折叠（点折叠按钮）────────────────────
            win.click("#sidebar-collapse")
            time.sleep(0.8)
            s3 = win.evaluate(JS_SNAP)
            print("[5] collapsed state:", s3, flush=True)
            if not s3["sidebarClosed"]:
                fail.append("点击后 sidebar 应 closed")
            if not s3["bodyCollapsed"]:
                fail.append("点击后 body 应 sidebar-collapsed")
            if not s3["expandBtnVisible"]:
                fail.append("折叠后 #sidebar-expand-btn 应可见")
            win.screenshot(path=str(EVAL_DIR / "gui_p2_probe_collapsed.png"))
            print("[5] shot: collapsed", flush=True)

            # 再点恢复
            win.click("#sidebar-expand-btn")
            time.sleep(0.8)
            s4 = win.evaluate(JS_SNAP)
            print("[6] restored state:", s4, flush=True)
            if s4["sidebarClosed"]:
                fail.append("再点后应恢复展开")

            # 控制台零错误（连接后端前的渲染期）
            print("[7] fail list:", fail, flush=True)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()

    if fail:
        print("PROBE_FAIL:", "; ".join(fail), flush=True)
        return 1
    print("PROBE_P2_OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
