// Bobo Desktop — TICKET-DESK-V4: 小组件开关状态 + 窗口尺寸持久化（纯 Node，无 electron 依赖，可单测）
// 只读写 data/desktop-config.json 的 widget_enabled / widget_size 字段；其余配置字段原样保留。
const fs = require('fs')
const path = require('path')

function configPath(dataDir) {
  return path.join(dataDir, 'desktop-config.json')
}

function readConfig(dataDir) {
  try {
    return JSON.parse(fs.readFileSync(configPath(dataDir), 'utf8'))
  } catch (_) {
    return {}
  }
}

function writeConfig(dataDir, cfg) {
  const p = configPath(dataDir)
  const dir = path.dirname(p)
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true })
  fs.writeFileSync(p, JSON.stringify(cfg, null, 2), 'utf8')
}

function readWidgetEnabled(dataDir, def = false) {
  const cfg = readConfig(dataDir)
  return cfg.widget_enabled === true
}

function writeWidgetEnabled(dataDir, enabled) {
  const cfg = readConfig(dataDir)
  cfg.widget_enabled = !!enabled
  writeConfig(dataDir, cfg)
  return cfg.widget_enabled
}

// TICKET-DESK-V4 追加②：窗口尺寸持久化（resize 时写回，重启恢复上次大小）
const MIN_W = 240
const MIN_H = 150

function clampSize(size) {
  const w = Math.max(MIN_W, Math.round(Number(size && size.width) || MIN_W))
  const h = Math.max(MIN_H, Math.round(Number(size && size.height) || MIN_H))
  return { width: w, height: h }
}

function readWidgetSize(dataDir) {
  const cfg = readConfig(dataDir)
  return clampSize(cfg.widget_size)
}

function writeWidgetSize(dataDir, size) {
  const cfg = readConfig(dataDir)
  cfg.widget_size = clampSize(size)
  writeConfig(dataDir, cfg)
  return cfg.widget_size
}

module.exports = { configPath, readWidgetEnabled, writeWidgetEnabled, readWidgetSize, writeWidgetSize, MIN_W, MIN_H }
