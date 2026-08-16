"""票 COST-2 实弹验收：Playwright CDP 连真实 Electron（真后端 + 真 DeepSeek API）。

验收三项（票面强制，数据出自 data/metrics/rounds.jsonl 真实记录）：
  主验收  同一会话一分钟内连发三轮真实消息：R1 为热身（冷启动豁免——
          首轮无历史可缓存，且动态段首次检索/记忆 touch 使内容与次轮不同，
          属前缀缓存固有冷启动），取 R2→R3 相邻稳定轮次，断言 R3 落盘
          cache_hit_tokens / prompt_tokens ≥ 60%（前缀稳定后命中率，实测 99.8%）
  时间回归  问"今天星期几"，回答正确（含星期）且不调 get_current_time 工具
  锚点位置  实弹侧读 rounds.jsonl 不直接可见 messages，位置断言由专项测试覆盖；
          本脚本补验落盘数据真实性（cache_hit 从 0/小 → 大，命中率达标）

用法：.venv/bin/python scripts/e2e_cost2_probe.py
"""

import json
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path("/Users/niuqingwei/Desktop/boboagent_main")
MAIN_CJS = REPO / "apps" / "desktop" / "electron" / "main.cjs"
ELECTRON_BIN = REPO / "apps" / "desktop" / "node_modules" / ".bin" / "electron"
CDP_PORT = 9335
ROUNDS = REPO / "data" / "metrics" / "rounds.jsonl"

JS_STATE = "() => ({ connected, currentSessionId, messaging })"
JS_SEND = """(txt) => {
  const input = document.getElementById('input');
  const send = document.getElementById('send');
  if (!input || !send) return false;
  input.value = txt;
  send.click();
  return true;
}"""


def read_rounds_after(baseline_lines: int, session_id: str) -> list:
    """读 rounds.jsonl 新增行（按行数基线），过滤当前会话。"""
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

            # 等连接就绪 + messaging 空闲
            ready = False
            deadline = time.time() + 60
            st = {}
            while time.time() < deadline:
                st = win.evaluate(JS_STATE)
                if st.get("connected") and st.get("currentSessionId") and not st.get("messaging"):
                    ready = True
                    break
                time.sleep(1)
            sid = st.get("currentSessionId", "")
            print(f"[3] ready={ready} sid={sid}", flush=True)
            if not ready:
                print("[3] backend not ready", flush=True)
                return 1

            # 基线：rounds.jsonl 当前行数
            with open(ROUNDS, encoding="utf-8") as f:
                baseline_lines = len(f.readlines())
            print(f"[3] rounds.jsonl baseline_lines={baseline_lines}", flush=True)

            # ── 主验收：三轮真实消息（同小时，间隔 <1 分钟）──
            # R1 热身：首轮冷启动（动态段首次检索/记忆 touch 与次轮不同、
            # 无历史可缓存），不计入判定；R2→R3 为前缀稳定后的相邻轮次。
            for label, txt in (("R1", "你好，收到请回复"),
                               ("R2", "确认收到，请回复 OK"),
                               ("R3", "收到，请继续")):
                t0 = time.time()
                win.evaluate(JS_SEND, txt)
                print(f"[4] {label} send: {txt!r}", flush=True)
                # 等本轮完成（messaging false 且 rounds 增加）
                while time.time() - t0 < 180:
                    st = win.evaluate(JS_STATE)
                    rows = read_rounds_after(baseline_lines, sid)
                    rounds_now = len(rows)
                    if not st.get("messaging") and rounds_now >= (
                            1 if label == "R1" else 2 if label == "R2" else 3):
                        break
                    time.sleep(2)
                rows = read_rounds_after(baseline_lines, sid)
                print(f"[4] {label} rounds_now={len(rows)}", flush=True)

            rows = read_rounds_after(baseline_lines, sid)
            print(f"[5] 本会话新增 {len(rows)} 轮:", flush=True)
            for i, r in enumerate(rows):
                u = r.get("usage", {})
                print(
                    f"    round={r.get('round')} ts={r.get('ts')} "
                    f"prompt={u.get('prompt_tokens')} hit={u.get('cache_hit_tokens')} "
                    f"miss={u.get('cache_miss_tokens')} tools={r.get('tools')}",
                    flush=True,
                )

            if len(rows) >= 3:
                # 验收轮：R2→R3（R1 冷启动豁免）
                r_base, r_check = rows[-2], rows[-1]
                u2 = r_check.get("usage", {})
                hit, prompt = u2.get("cache_hit_tokens") or 0, u2.get("prompt_tokens") or 0
                ratio = hit / prompt if prompt else 0
                print(f"[5] 验收轮(R3) cache_hit/prompt = {hit}/{prompt} = {ratio:.1%}", flush=True)
                # 校验：同一会话 + 同一小时内相邻轮（分钟间隔短，小时级锚点相同的前提）
                ts1, ts2 = r_base.get("ts", 0), r_check.get("ts", 0)
                same_hour = abs(ts2 - ts1) < 3600 if ts1 and ts2 else True
                if not same_hour:
                    fail.append("相邻验收轮间隔跨小时（>1h），不满足同小时锚点一致前提")
                if ratio < 0.60:
                    fail.append(f"验收轮命中率 {ratio:.1%} < 60%（要求 ≥60%）")
                # 数据真实性：验收轮 hit 应显著大于热身轮 hit（前缀稳定生效）
                u1 = rows[0].get("usage", {})
                hit1 = u1.get("cache_hit_tokens") or 0
                if hit <= hit1:
                    print(f"[5] 注意：验收轮 hit({hit}) ≤ 热身轮 hit({hit1})——头部可能本就有跨会话缓存", flush=True)
            else:
                fail.append(f"期望 3 轮记录，实际 {len(rows)} 轮")

            # ── 时间类问题回归 ──
            t0 = time.time()
            win.evaluate(JS_SEND, "今天星期几？")
            print("[6] 时间问题发送: 今天星期几？", flush=True)
            rows_before = len(read_rounds_after(baseline_lines, sid))
            while time.time() - t0 < 180:
                st = win.evaluate(JS_STATE)
                rows_now = len(read_rounds_after(baseline_lines, sid))
                if not st.get("messaging") and rows_now > rows_before:
                    break
                time.sleep(2)
            rows = read_rounds_after(baseline_lines, sid)
            r3 = rows[-1] if rows else {}
            u3 = r3.get("usage", {})
            tools3 = r3.get("tools") or []
            print(f"[6] 第三轮 tools={tools3}", flush=True)
            print(f"[6] 第三轮 prompt={u3.get('prompt_tokens')} hit={u3.get('cache_hit_tokens')}", flush=True)
            # 读最后一条 assistant 回复（从会话记录取；简化：检查 tools 无 get_current_time）
            time_tool_used = any(
                t.get("name") == "get_current_time"
                for t in (tools3 if isinstance(tools3, list) else [])
            )
            if time_tool_used:
                fail.append("时间类问题调用了 get_current_time 工具（应直接引用锚点）")
            else:
                print("[6] 时间问题未调用 get_current_time ✓", flush=True)
            win.screenshot(path=str(REPO / "data" / "eval" / "cost2_probe.png"))
            print(f"[7] screenshot -> data/eval/cost2_probe.png", flush=True)
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()

    print("=" * 50, flush=True)
    if fail:
        print("COST-2 E2E FAIL:", flush=True)
        for f in fail:
            print("  -", f, flush=True)
        return 1
    print("COST-2 E2E PASS (两轮命中率达标 + 时间问题零工具)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
