"""票 COST-3 实弹验收：Playwright CDP 连真实 Electron（真后端 + 真 DeepSeek API）。

验收两项（票面强制，数据出自 data/metrics/rounds.jsonl 真实记录）：
  a) 同会话连续 3 轮含工具调用：R2/R3 缓存命中 ≥85%
  b) 长会话场景（≥12 轮且含文件写入，触发压缩跳过路径）：末轮命中 ≥85%

实测四轮（2026-08-17）：b 三连过（93.7/93.6/95.5）；a 的 R3 波动 57-90%
（v5 90.2 / v6 77.9 / v7 57.1 / v8 78.7）。根因：DeepSeek 自动缓存对短会话
"上轮新增段"（模型回复+工具结果）缓存随机，R3.hit 恒等于 R2.hit（新增段
全 miss）时 R3.ratio < R2.ratio 是数学常态；引擎无 cache_control 控制权
（全库 0 匹配）。且 a 阶段不触发任何 COST-3 代码路径（无压缩/无锚点/工具集
不变），与修复无关。详见 library/agent开发/cost3终审E2E四轮实测数据.md。

构造：不设 BOCO_CONTEXT_BUDGET（该变量实为条数上限，设小值会触发真压缩断
前缀，v5 实证末轮塌至 53.3%）；默认预算下 12 轮内 history 逐字节不动。

用法：.venv/bin/python scripts/e2e_cost3_probe.py
"""

import json
import os
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path("/Users/niuqingwei/Desktop/boboagent_main")
MAIN_CJS = REPO / "apps" / "desktop" / "electron" / "main.cjs"
ELECTRON_BIN = REPO / "apps" / "desktop" / "node_modules" / ".bin" / "electron"
CDP_PORT = 9337
ROUNDS = REPO / "data" / "metrics" / "rounds.jsonl"
EVENTS = REPO / "data" / "logs" / "events.jsonl"

JS_STATE = "() => ({ connected, currentSessionId, messaging })"
JS_SEND = """(txt) => {
  const input = document.getElementById('input');
  const send = document.getElementById('send');
  if (!input || !send) return false;
  input.value = txt;
  send.click();
  return true;
}"""
# 票 COST-3 终审修②：点击侧栏 "+ 新对话" 按钮开全新会话。
# 桌面端渲染的是原生 HTML（apps/desktop/dist/index.html），新对话按钮 id 为
# #new-chat（dist/index.html:3146 addEventListener → newChat() → session.create
# → currentSessionId 更新）；React 版 .new-chat-btn 仅存在于 src/（未在桌面端加载）。
JS_CLICK_NEW_CHAT = """() => {
  const btn = document.getElementById('new-chat');
  if (!btn) return false;
  btn.click();
  return true;
}"""
# AUTO 开关：#auto-toggle 点击 → slash.exec 'auto'（携带 session_id，F4-6）→ 后端
# 翻转 auto_mode[sid]。新会话默认非 AUTO → 工具执行走人工确认，无人响应每步
# 挂 120s（实测 R2 卡死）。验收必须 AUTO：白名单命令静默执行、决策链自动放行。
JS_AUTO_STATE = """() => {
  const at = document.getElementById('auto-toggle');
  if (!at) return false;
  return at.classList.contains('on');
}"""
JS_CLICK_AUTO = """() => {
  const at = document.getElementById('auto-toggle');
  if (!at) return false;
  at.click();
  return true;
}"""


def ensure_auto(win, timeout: float = 15.0) -> bool:
    """点击 #auto-toggle 直至 .on（AUTO 开启）。点击是异步 RPC，需轮询。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if win.evaluate(JS_AUTO_STATE):
            return True
        win.evaluate(JS_CLICK_AUTO)
        time.sleep(1.5)
    return False

# 长会话消息池：12+ 轮，穿插文件写入轮（触发 _session_written_files + 压缩评估）
LONG_MSGS = [
    "请查看 data/eval/ 目录下有哪些文件（用 list_directory）",
    "请把 'cost3 长会话探针' 写入 data/eval/cost3_probe_tmp.txt（用 file_operation write）",
    "收到请回复 OK",
    "请再读一次 data/eval/cost3_probe_tmp.txt 的内容（用 read_local_file）",
    "确认内容无误，请回复 OK",
    "请追加一行 'second line' 到 data/eval/cost3_probe_tmp.txt（file_operation write 覆盖即可）",
    "收到，回复 OK",
    "请列出 tests/ 目录下 test_ticket_cost3.py 是否存在（list_directory tests/）",
    "确认存在，回复 OK",
    "请把 data/eval/cost3_probe_tmp.txt 内容改为 'final content'（file_operation write）",
    "收到，回复 OK",
    "最后确认：当前会话已写文件有哪些？",
]


def read_rounds_after(baseline_lines: int, session_id: str) -> list:
    rows = []
    with open(ROUNDS, encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines[baseline_lines:]:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("session_id") == session_id:
            rows.append(d)
    return rows


def read_events_after(baseline_lines: int, session_id: str, etype: str) -> list:
    """轮询 events.jsonl 中该会话的新事件（票 COST-3 终审修③：message.start 硬证据）。"""
    rows = []
    try:
        with open(EVENTS, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    for line in lines[baseline_lines:]:
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("session_id") == session_id and d.get("type") == etype:
            rows.append(d)
    return rows


def send_and_wait(win, txt, baseline_rounds, baseline_events, sid, expect_rounds):
    """发送消息：60s 内 message.start 必须到达（fail-fast 不许空转），随后等 rounds 落盘。"""
    t0 = time.time()
    win.evaluate(JS_SEND, txt)
    print(f"    send: {txt[:40]!r}", flush=True)
    # ① engine.thread.start 60s fail-fast——后端真实启动处理线程的硬证据（修③）
    #    实测：message.start 不落盘 events.jsonl（server_utils.emit 仅 JSON-RPC 转发
    #    前端 + metrics 轮缓冲）；engine.thread.start 由 engine_adapter.py:310 在每次
    #    用户消息启动引擎线程时写一条 events.jsonl，语义等价且更强（后端已开跑）。
    starts = 0
    while time.time() - t0 < 60:
        starts = len(read_events_after(baseline_events, sid, "engine.thread.start"))
        if starts >= expect_rounds:
            break
        time.sleep(1)
    if starts < expect_rounds:
        raise RuntimeError(
            f"engine.thread.start 60s 未到达（expect {expect_rounds} 实收 {starts}）"
            f"——消息未进后端，fail-fast 退出"
        )
    # ② 等 rounds.jsonl 落盘（LLM 处理慢，放宽到 300s）
    while time.time() - t0 < 300:
        st = win.evaluate(JS_STATE)
        rows = read_rounds_after(baseline_rounds, sid)
        if not st.get("messaging") and len(rows) >= expect_rounds:
            return rows
        time.sleep(2)
    return read_rounds_after(baseline_rounds, sid)


def ratio_of(rows, idx):
    r = rows[idx]
    u = r.get("usage", {})
    h, p = u.get("cache_hit_tokens") or 0, u.get("prompt_tokens") or 0
    return h, p, (h / p if p else 0), r.get("ts", 0), len(r.get("tools") or [])


def main():
    print("[1] spawn electron (CDP :%d) ..." % CDP_PORT, flush=True)
    env = dict(os.environ)
    # 票 COST-3 终审修复（v6）：不再设 BOBO_CONTEXT_BUDGET=8。
    # 该变量读作"消息条数硬上限"（_get_msg_count_budget → max(10,8)=10）：
    # 12 轮会话条数超 10 即触发 context.compressed 真压缩，压缩改写 history
    # 中段 → 后续轮前缀断裂 → 命中率塌（实测末轮 53.3%，hit 仅剩头部 1920）。
    # 跳过路径（compress_skipped）要求"条数不超限"才可能发生，条数触发永远
    # 不跳过。COST-3 验收口径 = 12 轮含文件写入末轮 ≥85%：保持默认 200 条上限
    # + 默认 budget ratio，12 轮内 history 逐字节不动，前缀全程稳定。
    # 注意：这里刻意不用 print 提到 BOBO_CONTEXT_BUDGET（误导已删除）。
    # 票 COST-3 终审修①：--user-data-dir 隔离 profile，不继承任何历史会话态
    profile_dir = f"/tmp/cost3_profile_{int(time.time())}"
    proc = subprocess.Popen(
        [str(ELECTRON_BIN), str(MAIN_CJS),
         f"--remote-debugging-port={CDP_PORT}", f"--user-data-dir={profile_dir}"],
        cwd=str(REPO), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    print(f"[1] profile 隔离: {profile_dir}", flush=True)
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
                        if "index.html" in pg.url:
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
            win.wait_for_selector("#input", timeout=60000)

            ready = False
            deadline = time.time() + 120
            st = {}
            while time.time() < deadline:
                st = win.evaluate(JS_STATE)
                if st.get("connected") and st.get("currentSessionId") and not st.get("messaging"):
                    ready = True
                    break
                time.sleep(1)
            sid = st.get("currentSessionId", "")
            print(f"[3] ready={ready} sid={sid} st={st}", flush=True)
            if not ready:
                return 1

            # 票 COST-3 终审修②：点 "+ 新对话" 开全新会话，断言 sid 为当天新值
            # （20260812 死会话复活实证根因：不点新对话则继承启动时恢复的旧会话）
            clicked = win.evaluate(JS_CLICK_NEW_CHAT)
            if not clicked:
                print("[3b] FAIL: 未找到 .new-chat-btn", flush=True)
                return 1
            deadline = time.time() + 30
            new_sid = ""
            while time.time() < deadline:
                st = win.evaluate(JS_STATE)
                cand = str(st.get("currentSessionId") or "")
                if cand and cand != sid:
                    new_sid = cand
                    break
                time.sleep(1)
            today = time.strftime("%Y%m%d")
            if not new_sid.startswith(today):
                print(f"[3b] FAIL: 新会话 sid={new_sid!r} 非当天新值（期望 {today}* 前缀）", flush=True)
                return 1
            sid = new_sid
            print(f"[3b] 新对话 sid={sid}（当天新值 ✓）", flush=True)

            # 新会话默认非 AUTO → 工具执行走人工确认无人响应（每步挂 120s）。
            # 验收必须 AUTO：白名单命令静默执行、决策链自动放行，不阻塞。
            if not ensure_auto(win):
                print("[3c] FAIL: AUTO 模式未能开启", flush=True)
                return 1
            print("[3c] AUTO 模式已开启 ✓", flush=True)

            with open(ROUNDS, encoding="utf-8") as f:
                baseline_lines = len(f.readlines())
            with open(EVENTS, encoding="utf-8") as f:
                baseline_events = len(f.readlines())
            print(f"[3] rounds.jsonl baseline_lines={baseline_lines} "
                  f"events.jsonl baseline_lines={baseline_events}", flush=True)

            # ── a) 3 轮含工具调用 ──
            for i, txt in enumerate(["你好，收到请回复", "请用 list_directory 工具查看 data/ 目录内容", "确认收到，请回复 OK"]):
                send_and_wait(win, txt, baseline_lines, baseline_events, sid, i + 1)
            rows = read_rounds_after(baseline_lines, sid)
            print(f"[4] 前 3 轮: rounds={len(rows)}", flush=True)
            for i in range(min(3, len(rows))):
                h, p, ratio, ts, ntools = ratio_of(rows, i)
                print(f"    R{i+1} prompt={p} hit={h} ratio={ratio:.1%} tools={ntools}", flush=True)
            if len(rows) >= 3:
                h2, p2, r2 = ratio_of(rows, 1)[:3]
                h3, p3, r3 = ratio_of(rows, 2)[:3]
                if r2 < 0.85:
                    fail.append(f"验收 a: R2 命中率 {r2:.1%} < 85%")
                if r3 < 0.85:
                    fail.append(f"验收 a: R3 命中率 {r3:.1%} < 85%")
                tools_used = [t for i in range(3) for t in (rows[i].get("tools") or [])]
                if not any(t.get("name") == "list_directory" for t in tools_used):
                    print("    [注意] R2 未见 list_directory 工具调用，重试一轮", flush=True)
                    send_and_wait(win, "请用 list_directory 工具查看 data/ 目录内容", baseline_lines, baseline_events, sid, 4)
                    rows = read_rounds_after(baseline_lines, sid)
            else:
                fail.append("验收 a: 期望 ≥3 轮，实际不足")

            # ── b) 长会话 ≥12 轮含文件写入 ──
            start_len = len(rows)
            target = max(12, start_len + 1)
            for j, txt in enumerate(LONG_MSGS):
                if len(read_rounds_after(baseline_lines, sid)) >= target:
                    break
                send_and_wait(win, txt, baseline_lines, baseline_events, sid, start_len + j + 1)
            rows = read_rounds_after(baseline_lines, sid)
            print(f"[5] 长会话轮数: {len(rows)}", flush=True)
            if len(rows) >= 12:
                h_last, p_last, r_last = ratio_of(rows, -1)[:3]
                print(f"    末轮 prompt={p_last} hit={h_last} ratio={r_last:.1%}", flush=True)
                if r_last < 0.85:
                    fail.append(f"验收 b: 末轮命中率 {r_last:.1%} < 85%（{len(rows)} 轮）")
                # 已写文件轮是否存在
                tools_used = [t.get("name") for r in rows for t in (r.get("tools") or [])]
                if "file_operation" not in tools_used and "write_file" not in tools_used:
                    print("    [注意] 未见文件写入工具调用", flush=True)
            else:
                fail.append(f"验收 b: 期望 ≥12 轮，实际 {len(rows)} 轮")
            win.screenshot(path=str(REPO / "data" / "eval" / "cost3_probe.png"))
            print(f"[6] screenshot -> data/eval/cost3_probe.png", flush=True)
            browser.close()
    finally:
        # 票 COST-3 终审修③：退出前清理自己的 Electron 实例——CDP 断开 + 主进程
        # SIGTERM → main.cjs before-quit → stopBackend 连坐杀后端，不留孤儿
        if "browser" in locals() and browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except Exception:
                pass

    print("=" * 50, flush=True)
    if fail:
        print("COST-3 E2E FAIL:", flush=True)
        for f in fail:
            print("  -", f, flush=True)
        return 1
    print("COST-3 E2E PASS (a: 3 轮含工具 R2/R3 ≥85% + b: 长会话末轮 ≥85%)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
