#!/bin/bash
# pi_chat.sh — 启动 Bobo↔pi tmux 双 TUI 对话舞台
#
# 布局：
#   ┌────────────────┬────────────────┐
#   │ bobo TUI       │  pi TUI        │
#   ├────────────────┴────────────────┤
#   │ relay 状态行（进度 / 轮数 / 结果）│
#   └─────────────────────────────────┘
#
# 用法：
#   ./pi_chat.sh [轮数]      # 默认 5 轮
#   ./pi_chat.sh 3           # 3 轮
#
# 之后在 bobo pane（左侧）输入话题，relay 会自动接管，
# 把两边回复互相传递，走完 N 轮后截屏并通知。

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$SCRIPT_DIR"

ROUNDS="${1:-5}"
SESSION="bobo-pi-chat"
LOG="$ROOT/data/pi_relay.log"
mkdir -p "$ROOT/data"

# 清理旧会话（如果还挂着）
tmux kill-session -t "$SESSION" 2>/dev/null || true

echo "▶ 启动 tmux 会话 $SESSION（$ROUNDS 轮）…"

# 1) 会话 + 基础配置
tmux new-session -d -s "$SESSION" -x 230 -y 55
tmux set-option -g extended-keys on

# 2) 左侧 bobo TUI（pane 0）
tmux send-keys -t "$SESSION:0.0" "cd $ROOT/ui-tui && npx tsx src/entry.tsx" Enter

# 3) 右侧 pi TUI（pane 1）
tmux split-window -h -t "$SESSION:0.0"
tmux send-keys -t "$SESSION:0.1" "pi" Enter

# 4) 底部 relay 状态条：在 pi（右）下方切 5 行高的 pane（pane 2）
tmux split-window -v -t "$SESSION:0.1" -l 5
tmux send-keys -t "$SESSION:0.2" "echo '=== relay 状态 ==='; exec tail -f $LOG" Enter

# 5) 启动 relay（后台，日志写文件；tail -f 在 pane2 实时显示）
RELAY_BOBO_PANE="$SESSION:0.0" \
RELAY_PI_PANE="$SESSION:0.1" \
RELAY_STATUS_PANE="$SESSION:0.2" \
nohup "$ROOT/.venv/bin/python" "$ROOT/tools/pi_relay.py" "$ROUNDS" \
    > "$LOG" 2>&1 &

echo "✓ 已启动。attach 到会话：tmux attach -t $SESSION"
echo "  在 bobo（左侧）输入话题，relay 自动接管对话。"
