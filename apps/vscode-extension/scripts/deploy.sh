#!/usr/bin/env bash
# deploy.sh — TICKET-VSC-1B 实弹部署脚本（Kimi 终审复跑用）
#
# 用途：把仓库 apps/vscode-extension/ 的最新产物部署到 VS Code 安装目录
#       （~/.vscode/extensions/bobo-local.bobo-vscode-0.1.0/），
#       保持"本地安装链路行为不变"（不发布 marketplace，直接拷贝）。
#
# 复跑步骤：
#   1. ./scripts/deploy.sh          # 编译 + 拷贝 + 自校验
#   2. 在 VS Code 里 Cmd+Shift+P → "Developer: Reload Window" 重载
#   3. 按下方"实弹验收清单"逐条操作
#
# 实弹验收清单（对应票验收 4a-4d）：
#   a. Activity Bar 出现 bobo 图标（终端窗口单线条 SVG）→ 点击展开侧边栏面板
#   b. 打开任意文件选中一段代码 → 面板顶部"当前选中"卡片实时显示
#      （文件 + 行区间 + 代码预览，≤500 字符）
#   c. 右键选中代码 → "Ask bobo"（或 Cmd+Shift+B）→ 面板流式收到回答，
#      不再出现 "not connected"
#   d. kill 桌面端 bobo 进程 → 重启桌面端 → 不重启 VS Code，再 Ask bobo
#      → 自动恢复（重连后重新 session.create 并绑定新 sid）

set -euo pipefail
cd "$(dirname "$0")/.."

EXT_DIR="${HOME}/.vscode/extensions/bobo-local.bobo-vscode-0.1.0"
if [ ! -d "$EXT_DIR" ]; then
  echo "ERROR: 未找到安装目录 $EXT_DIR" >&2
  exit 1
fi

echo "[1/4] npm run compile（产物同步）"
npm run compile

echo "[2/4] 拷贝 out/ + package.json + media/ 到安装目录"
rm -rf "$EXT_DIR/out"
cp -R out "$EXT_DIR/out"
cp package.json "$EXT_DIR/package.json"
rm -rf "$EXT_DIR/media"
cp -R media "$EXT_DIR/media"

echo "[3/4] 自校验"
grep -q '"id": "bobo"' "$EXT_DIR/package.json" && echo "  ✓ viewsContainers.activitybar 含 bobo 容器"
grep -q '"id": "boboChat"' "$EXT_DIR/package.json" && echo "  ✓ views.bobo 含 boboChat 视图"
grep -q 'onView:boboChat' "$EXT_DIR/package.json" && echo "  ✓ activationEvents 含 onView:boboChat"
[ -f "$EXT_DIR/media/bobo.svg" ] && echo "  ✓ media/bobo.svg 已部署"
[ -f "$EXT_DIR/out/sessionFlow.js" ] && echo "  ✓ out/sessionFlow.js 已部署"

echo "[4/4] 完成。请在 VS Code 执行 'Developer: Reload Window' 后按验收清单操作。"
