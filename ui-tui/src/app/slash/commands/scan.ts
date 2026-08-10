import { patchOverlayState } from '../../overlayStore.js'
import type { SlashCommand } from '../types.js'

/**
 * TICKET-SCAN-L4-2：/scan — 打开端点选择器（键盘弹窗）。
 *
 * 与后端 /scan（侦查 tmux 并列出候选）的关系：本命令在前端拦截，打开
 * ScanPicker overlay；overlay mount 时自动调后端 slash.exec scan 拿候选，
 * ↑/↓ 选端点、Enter 即连（自动 /connect <编号>，轮数交给后端 L4-1 自主评估），
 * 不再需要手动记编号 + 输轮数。
 *
 * 后端 /scan 本就忽略参数，这里带参也一律打开选择器，行为与后端一致。
 */
export const scanCommands: SlashCommand[] = [
  {
    help: 'pick a peer endpoint to chat with (↑/↓ select, Enter connect)',
    name: 'scan',
    run: () => {
      patchOverlayState({ scanPicker: true })
    }
  }
]
