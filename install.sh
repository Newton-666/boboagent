#!/usr/bin/env bash
# Bobo Agent — 一行命令安装脚本
# curl -sSL https://raw.githubusercontent.com/Newton-666/boboagent/main/install.sh | bash

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     Bobo Agent — 一键安装           ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""

# ── Python ──
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo -e "${RED}未检测到 Python。请先安装 Python 3.10+${NC}"
    echo "  https://www.python.org/downloads/"
    exit 1
fi
echo -e "${GREEN}✓${NC} Python: $($PYTHON --version)"

# ── Node ──
if ! command -v node &>/dev/null; then
    echo -e "${YELLOW}⚠${NC} 未检测到 Node.js（TUI 依赖）"
    echo "  macOS:  brew install node"
    echo "  Ubuntu: sudo apt install nodejs npm"
    echo ""
    echo -e "${YELLOW}安装会继续，但首次启动前请安装 Node.js${NC}"
    echo ""
fi

# ── Install ──
echo "正在安装 bobo-agent ..."
$PYTHON -m pip install --quiet git+https://github.com/Newton-666/boboagent.git 2>&1 || {
    echo -e "${RED}pip install 失败，请检查网络${NC}"
    exit 1
}
echo -e "${GREEN}✓${NC} bobo-agent 安装完成"

# ── Done ──
echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     安装完成！                      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""
echo "  启动:  ${CYAN}bobo${NC}"
echo "  首次启动自动弹出配置向导（选 provider + 输 API key）"
echo "  切换模型: ${CYAN}/model${NC}"
