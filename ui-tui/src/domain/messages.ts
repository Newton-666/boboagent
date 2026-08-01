import { LONG_MSG } from '../config/limits.js'
import { buildToolTrailLine, fmtK } from '../lib/text.js'
import type { Msg, SessionInfo } from '../types.js'

export const introMsg = (info: SessionInfo): Msg => ({ info, kind: 'intro', role: 'system', text: '' })

export const imageTokenMeta = (info?: ImageMeta | null) => {
  const { width, height, token_estimate: t } = info ?? {}

  return [width && height ? `${width}x${height}` : '', (t ?? 0) > 0 ? `~${fmtK(t!)} tok` : '']
    .filter(Boolean)
    .join(' · ')
}

export const attachedImageNotice = (info?: ({ name?: string } & ImageMeta) | null) => {
  const meta = imageTokenMeta(info)
  const label = info?.name ? `📎 Attached image: ${info.name}` : '📎 Attached image'

  return `${label}${meta ? ` · ${meta}` : ''}`
}

export const userDisplay = (text: string) => {
  if (text.length <= LONG_MSG) {
    return text
  }

  const first = text.split('\n')[0]?.trim() ?? ''
  const words = first.split(/\s+/).filter(Boolean)
  const prefix = (words.length > 1 ? words.slice(0, 4).join(' ') : first).slice(0, 80)

  return `${prefix || '(message)'} [long message]`
}

/** 内部注入段标记前缀——命中则不在 TUI 展示，仅 LLM 可见。introMsg（text=''）不受影响。 */
const INTERNAL_SYSTEM_PREFIXES: readonly string[] = [
  '[工作锚点',
  '[阶段完成摘要',
  '⚠️ 历史已压缩',
  '【上下文自查协议】',
  '[最近读过的文件]',
  '[已注册的自定义 API]',
  '[项目规则 (AGENTS.md)]',
  '📝 本会话已产出笔记',
  '注意：这个任务涉及多个步骤或文件',
  '注意：检测到多步任务但未建台账',
  '翻阅纪律：',
  '[对话历史摘要]',
  '[Bobo 注意到]',
  '[验证]',
  '## 可用的项目标准',
]

const isInternalSystemMsg = (text: string) =>
  INTERNAL_SYSTEM_PREFIXES.some(prefix => text.startsWith(prefix))

export const toTranscriptMessages = (rows: unknown): Msg[] => {
  if (!Array.isArray(rows)) {
    return []
  }

  const out: Msg[] = []
  let pending: string[] = []

  for (const row of rows) {
    if (!row || typeof row !== 'object') {
      continue
    }

    const { context, name, role, text } = row as TranscriptRow

    if (role === 'tool') {
      pending.push(buildToolTrailLine(name ?? 'tool', context ?? ''))

      continue
    }

    if (typeof text !== 'string' || !text.trim()) {
      continue
    }

    if (role === 'assistant') {
      out.push({ role, text, ...(pending.length && { tools: pending }) })
      pending = []
    } else if (role === 'user') {
      out.push({ role, text })
      pending = []
    } else if (role === 'system') {
      // 票 TICKET-022：过滤内部注入的 system 消息，不对 TUI 用户可见
      if (isInternalSystemMsg(text)) {
        continue
      }
      out.push({ role, text })
      pending = []
    }
  }

  return out
}

export const fmtDuration = (ms: number) => {
  const t = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(t / 3600)
  const m = Math.floor((t % 3600) / 60)
  const s = t % 60

  return h > 0 ? `${h}h ${m}m` : m > 0 ? `${m}m ${s}s` : `${s}s`
}

interface ImageMeta {
  height?: number
  token_estimate?: number
  width?: number
}

interface TranscriptRow {
  context?: string
  name?: string
  role?: string
  text?: string
}
