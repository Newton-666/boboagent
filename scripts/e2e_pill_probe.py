"""TICKET-DESK-V2D5 ⓪：Playwright 实弹取证（CDP 连 Electron）—— 药丸链路逐环定位断点。

方案：起真实 Electron（带 --remote-debugging-port），Chromium CDP 直连渲染进程。
不起假壳、不 mock —— 真后端（python -m bobo_tui_gateway.entry）完整跑。

用法：.venv/bin/python scripts/e2e_pill_probe.py [--send "hi"] [--wait 30]

逐环取证：
  A. 连接就绪后读 currentSessionId / connected / boboAPI
  B. 手动 call('context.stats') 打印原始返回（后端应答是否到达渲染层）
  C. 读 #ctx-pill-text 当前文本（复现恒 0% · 0/128K）
  D. 可选 --send：发一条真实消息，回合结束后再读药丸
截图落盘 /tmp/pill_probe.png
"""

import argparse
import json
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path("/Users/niuqingwei/Desktop/boboagent_main")
MAIN_CJS = REPO / "apps" / "desktop" / "electron" / "main.cjs"
ELECTRON_BIN = REPO / "apps" / "desktop" / "node_modules" / ".bin" / "electron"
CDP_PORT = 9333

JS_PROBE = """
() => ({ currentSessionId, connected, hasAPI: !!window.boboAPI, reqId })
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

JS_PILL = """
() => {
  const t = document.getElementById('ctx-pill-text');
  const f = document.getElementById('ctx-pill-fill');
  const d = document.getElementById('ctx-stats-detail');
  return {
    text: t ? t.textContent : 'NO #ctx-pill-text',
    fillWidth: f ? f.style.width : 'NO #ctx-pill-fill',
    detail: d ? d.innerHTML.slice(0, 200) : 'NO #ctx-stats-detail',
  };
}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", default=None, help="发送的真实消息文本（测回合结束上涨）")
    ap.add_argument("--wait", type=float, default=30, help="就绪等待秒数")
    ap.add_argument("--shot", default="/tmp/pill_probe.png")
    args = ap.parse_args()

    # 1. 起真实 Electron（后端随 main.cjs 自动 spawn）
    print("[1] spawn electron (CDP :%d) ..." % CDP_PORT, flush=True)
    proc = subprocess.Popen(
        [str(ELECTRON_BIN), str(MAIN_CJS), f"--remote-debugging-port={CDP_PORT}"],
        cwd=str(REPO),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    try:
        with sync_playwright() as p:
            # 2. 连 CDP，找主窗口（URL 含 dist/index.html）
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
            for ctx in browser.contexts:
                for pg in ctx.pages:
                    u = pg.url
                    if "index.html" in u or "dist" in u:
                        win = pg
                        break
                if win:
                    break
            if not win:
                # 无页面：等 electron 拉起后重试
                for _ in range(20):
                    for ctx in browser.contexts:
                        for pg in ctx.pages:
                            if "index.html" in pg.url or "dist" in pg.url:
                                win = pg
                                break
                    if win:
                        break
                    time.sleep(1.5)
            if not win:
                print("[2] main window not found; pages:", flush=True)
                for ctx in browser.contexts:
                    for pg in ctx.pages:
                        print("   ", pg.url, flush=True)
                return 1
            win.wait_for_load_state("domcontentloaded", timeout=60000)
            win.wait_for_selector("#ctx-pill-text", timeout=60000)
            print("[2] window loaded", flush=True)

            # 3. 等连接就绪
            ready = False
            deadline = time.time() + args.wait
            st = {}
            while time.time() < deadline:
                st = win.evaluate("() => ({ connected, currentSessionId })")
                if st["connected"] and st["currentSessionId"]:
                    ready = True
                    break
                time.sleep(1)
            print(f"[3] ready={ready} state={json.dumps(st, ensure_ascii=False)}", flush=True)

            # A. 环境探针
            probe = win.evaluate(JS_PROBE)
            print(f"[A] probe: {json.dumps(probe, ensure_ascii=False)}", flush=True)

            # B. 手动 call context.stats
            stats = win.evaluate(JS_CALL_STATS)
            print(f"[B] call('context.stats') -> {json.dumps(stats, ensure_ascii=False)[:700]}", flush=True)

            # C. 药丸当前文本（复现）
            pill = win.evaluate(JS_PILL)
            print(f"[C] pill: {json.dumps(pill, ensure_ascii=False)}", flush=True)
            win.screenshot(path=args.shot)
            print(f"[C] screenshot -> {args.shot}", flush=True)

            # D. 可选：发真实消息
            if args.send:
                print(f"[D] send: {args.send!r}", flush=True)
                win.evaluate(
                    """(txt) => {
                        const input = document.getElementById('input');
                        input.value = txt;
                        document.getElementById('send').click();
                    }""",
                    args.send,
                )
                t0 = time.time()
                pill2 = None
                while time.time() - t0 < 180:
                    pill2 = win.evaluate(JS_PILL)
                    busy = win.evaluate("() => messaging")
                    if not busy and pill2["text"] != pill["text"]:
                        break
                    time.sleep(2)
                print(f"[D] after round: {json.dumps(pill2, ensure_ascii=False)}", flush=True)
                win.screenshot(path=args.shot.replace(".png", "_after.png"))
                print(f"[D] screenshot -> {args.shot.replace('.png', '_after.png')}", flush=True)

            browser.close()
        print("[done]", flush=True)
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
