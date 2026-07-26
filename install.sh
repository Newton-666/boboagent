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

# ── 1. Python version check ──────────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ] 2>/dev/null; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "${RED}未检测到 Python 3.10+。${NC}"
    # 尝试显示当前版本
    for cmd in python3 python; do
        if command -v "$cmd" &>/dev/null; then
            cur=$("$cmd" --version 2>&1)
            echo -e "  当前版本: ${YELLOW}$cur${NC}"
            break
        fi
    done
    echo ""
    echo "  安装 Python 3.10+:"
    echo "    macOS:  brew install python@3.12"
    echo "    Ubuntu: sudo apt install python3.12"
    echo "    官网:   https://www.python.org/downloads/"
    exit 1
fi
echo -e "${GREEN}✓${NC} Python: $($PYTHON --version)"

# ── 2. Node check (warn, don't block) ────────────────────────────────
if ! command -v node &>/dev/null; then
    echo -e "${YELLOW}⚠${NC} 未检测到 Node.js（TUI 依赖）"
    echo "  macOS:  brew install node"
    echo "  Ubuntu: sudo apt install nodejs npm"
    echo ""
    echo -e "${YELLOW}安装会继续，但首次启动前请安装 Node.js${NC}"
    echo ""
fi

# ── 3. Install ───────────────────────────────────────────────────────
echo "正在安装 bobo-agent ..."

PIP_LOG=$(mktemp)
PIP_FAILED=false
VENV_INSTALLED=false  # 标记是否为 venv 安装（跳过通用 PATH 警告）

# Try: user-site first (handles PEP 668 EXTERNALLY-MANAGED)
$PYTHON -m pip install --user --quiet git+https://github.com/Newton-666/boboagent.git >"$PIP_LOG" 2>&1 || PIP_FAILED=true

if $PIP_FAILED; then
    # If --user failed, try pipx
    if command -v pipx &>/dev/null; then
        echo "  --user 失败，尝试 pipx ..."
        if pipx install git+https://github.com/Newton-666/boboagent.git >"$PIP_LOG" 2>&1; then
            PIP_FAILED=false
        fi
    fi
fi

if $PIP_FAILED; then
    # If pipx also failed or not available, try venv
    echo "  pip 直装失败，创建 venv ..."
    VENV_DIR="$HOME/.bobo/venv"
    $PYTHON -m venv "$VENV_DIR" 2>/dev/null || true
    if [ -f "$VENV_DIR/bin/python" ]; then
        if "$VENV_DIR/bin/python" -m pip install --quiet git+https://github.com/Newton-666/boboagent.git >"$PIP_LOG" 2>&1; then
            PIP_FAILED=false
            VENV_INSTALLED=true
            echo -e "${GREEN}✓${NC} 已安装到 $VENV_DIR"
            echo ""
            echo -e "  启动: ${CYAN}$VENV_DIR/bin/bobo${NC}"
            echo ""
            echo "  添加 alias（推荐）："
            echo "    echo 'alias bobo=\"$VENV_DIR/bin/bobo\"' >> ~/.zshrc && source ~/.zshrc"
        fi
    fi
fi

if $PIP_FAILED; then
    echo -e "${RED}安装失败。错误信息：${NC}"
    tail -20 "$PIP_LOG"
    echo ""
    echo "常见原因："
    echo "  - Python 版本 < 3.10（当前: $($PYTHON --version)）"
    echo "  - 网络无法访问 GitHub（需要代理或 VPN）"
    echo "  - pip 版本过旧（运行: $PYTHON -m pip install --upgrade pip）"
    echo "  - PEP 668 限制（可尝试: pipx install bobo-agent）"
    rm -f "$PIP_LOG"
    exit 1
fi

rm -f "$PIP_LOG"
echo -e "${GREEN}✓${NC} bobo-agent 安装完成"

# ── 4. PATH check ────────────────────────────────────────────────────
BOBO_OK=true
if ! command -v bobo &>/dev/null; then
    BOBO_OK=false
fi

echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     安装完成！                      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
echo ""

if $VENV_INSTALLED; then
    # venv 安装：已在上面给出 alias 引导，不重复 PATH 警告
    :
elif $BOBO_OK; then
    echo "  启动 Bobo:"
    echo -e "    ${CYAN}bobo${NC}"
else
    echo -e "  ${YELLOW}bobo 命令不在 PATH 上。${NC}"
    # 从 Python user-site 推导 bobo 安装位置
    USER_BIN=$($PYTHON -c "import sysconfig; print(sysconfig.get_path('scripts', 'posix_user'))" 2>/dev/null || echo "")
    if [ -n "$USER_BIN" ] && [ -f "$USER_BIN/bobo" ]; then
        BOBO_PATH="$USER_BIN/bobo"
        echo "    已找到: $BOBO_PATH"
        echo ""
        echo "    添加 PATH（推荐）："
        echo "      echo 'export PATH=\"$USER_BIN:\$PATH\"' >> ~/.zshrc"
        echo "      source ~/.zshrc"
    else
        echo "    尝试查找: find ~/Library/Python ~/.local -name bobo 2>/dev/null"
        echo "    找到后将所在目录加入 PATH"
    fi
fi
echo ""
echo "  首次启动自动弹出配置向导（选 provider + 输 API key）"
echo "  切换模型: ${CYAN}/model${NC}"
