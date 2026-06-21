#!/bin/bash
# Bobo Desktop Installer
# Usage: bash install.sh [path/to/Bobo.dmg]
#   If no path given, downloads from GitHub release.

set -e

BOBO_DMG="${1:-}"
RELEASE_URL="https://github.com/Newton-666/boboagent/releases/latest/download/Bobo-0.1.0-arm64.dmg"

echo "=============================="
echo "  Bobo Desktop Installer"
echo "=============================="
echo ""

# ── Check Python 3 ──
if ! command -v python3 &>/dev/null; then
  echo "❌ 未找到 python3，请先安装 Python 3"
  echo "   https://www.python.org/downloads/"
  exit 1
fi
PYTHON_VER=$(python3 --version 2>&1)
echo "✅ 检测到 Python: $PYTHON_VER"

# ── Obtain .dmg ──
if [ -z "$BOBO_DMG" ]; then
  echo "📥 正在下载 Bobo.dmg..."
  BOBO_DMG="/tmp/Bobo.dmg"
  if command -v curl &>/dev/null; then
    curl -L -o "$BOBO_DMG" "$RELEASE_URL"
  elif command -v wget &>/dev/null; then
    wget -O "$BOBO_DMG" "$RELEASE_URL"
  else
    echo "❌ 未找到 curl 或 wget"
    exit 1
  fi
  echo "   下载完成"
fi

if [ ! -f "$BOBO_DMG" ]; then
  echo "❌ 找不到文件: $BOBO_DMG"
  exit 1
fi

# ── Mount .dmg ──
echo "📂 正在挂载磁盘映像..."
MOUNT_POINT=$(hdiutil attach -nobrowse "$BOBO_DMG" 2>/dev/null | tail -1 | awk '{print $3}')
if [ -z "$MOUNT_POINT" ]; then
  echo "❌ 挂载失败"
  exit 1
fi
echo "   已挂载到: $MOUNT_POINT"

# ── Install .app ──
echo "📦 正在安装到 /Applications..."
rm -rf "/Applications/Bobo.app" 2>/dev/null
cp -R "$MOUNT_POINT/Bobo.app" "/Applications/" 2>/dev/null || {
  echo "❌ 复制失败（可能需要 sudo）"
  hdiutil detach "$MOUNT_POINT" &>/dev/null
  sudo cp -R "$MOUNT_POINT/Bobo.app" "/Applications/"
  echo "   已通过 sudo 完成"
}

# ── Unmount ──
hdiutil detach "$MOUNT_POINT" &>/dev/null
echo "   已卸载磁盘映像"

# ── Remove quarantine ──
xattr -rd com.apple.quarantine "/Applications/Bobo.app" 2>/dev/null
echo "🔓 已解除隔离标记"

# ── First launch: install backend + create CLI ──
echo "🚀 首次启动（安装后端组件）..."
open -W -a "Bobo" --args --install-only 2>/dev/null || \
  open -W -a "Bobo" 2>/dev/null || true
sleep 5

# ── Check if backend was installed ──
if [ -d ~/.bobo/core ] && [ -d ~/.bobo/bin ]; then
  echo "✅ 后端已安装到 ~/.bobo/"
  echo ""
  echo "🔗 添加 bobo 命令到 PATH:"
  echo "   echo 'export PATH=\"\$HOME/.bobo/bin:\$PATH\"' >> ~/.zshrc"
  echo "   source ~/.zshrc"
  echo "   之后在终端输入 bobo 即可启动 TUI"
  echo ""
  echo "🎉 Bobo 安装完成！"
  echo "   启动: open /Applications/Bobo.app"
else
  echo "⚠️  后端安装可能未完成，请手动启动 Bobo 应用"
fi
