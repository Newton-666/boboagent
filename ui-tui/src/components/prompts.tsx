import { Box, Text, useInput } from '@hermes/ink'
import { useState } from 'react'

import { isMac } from '../lib/platform.js'
import type { Theme } from '../theme.js'
import type { ApprovalReq, ClarifyReq, ConfirmReq } from '../types.js'

import { TextInput } from './textInput.js'

const OPTS = ['once', 'session', 'always', 'deny'] as const
const LABELS = { always: 'Always allow', deny: 'Deny', once: 'Allow once', session: 'Allow this session' } as const
const CMD_PREVIEW_LINES = 10

type ApprovalKey = {
  downArrow?: boolean
  escape?: boolean
  return?: boolean
  upArrow?: boolean
}

type ApprovalAction =
  | { kind: 'choose'; choice: (typeof OPTS)[number] }
  | { kind: 'move'; delta: -1 | 1 }
  | { kind: 'noop' }

/**
 * Pure key-dispatch for the approval prompt — exported so the regression
 * matrix (Esc, Ctrl+C-equivalent, number keys, Enter, ↑↓) is testable
 * without mounting React + Ink + a fake stdin.  The component just maps the
 * action onto its own state setters.
 *
 * Esc and number keys both terminate the prompt; Esc maps to deny (parity
 * with the global Ctrl+C handler that already calls cancelOverlayFromCtrlC
 * for approvals).  Numbers 1..OPTS.length pick the labelled choice.  Enter
 * confirms the current selection.  ↑/↓ moves the selection within bounds.
 */
export function approvalAction(ch: string, key: ApprovalKey, sel: number): ApprovalAction {
  if (key.escape) {
    return { kind: 'choose', choice: 'deny' }
  }

  const n = parseInt(ch, 10)

  if (n >= 1 && n <= OPTS.length) {
    return { kind: 'choose', choice: OPTS[n - 1]! }
  }

  if (key.return) {
    return { kind: 'choose', choice: OPTS[sel]! }
  }

  if (key.upArrow && sel > 0) {
    return { kind: 'move', delta: -1 }
  }

  if (key.downArrow && sel < OPTS.length - 1) {
    return { kind: 'move', delta: 1 }
  }

  return { kind: 'noop' }
}

export function ApprovalPrompt({ onChoice, req, t }: ApprovalPromptProps) {
  // 按键处理现在在全局 useInputHandlers 中完成
  // 这里只负责渲染，sel 状态由全局 handler 中的 approvalSelRef 管理
  // 但为了显示效果，我们仍然需要知道当前选中项
  // 由于无法直接从 ref 读取，我们用一个简单的 useState
  // 实际上按键由全局 handler 处理，这里只做显示
  const [sel, setSel] = useState(0)

  // 仍然保留 useInput 作为后备，但全局 handler 会先处理
  useInput((ch, key) => {
    const action = approvalAction(ch, key, sel)

    if (action.kind === 'choose') {
      onChoice(action.choice)
    } else if (action.kind === 'move') {
      setSel(s => s + action.delta)
    }
  })

  const rawLines = req.command.split('\n')
  const shown = rawLines.slice(0, CMD_PREVIEW_LINES)
  const overflow = rawLines.length - shown.length

  return (
    <Box borderColor={t.color.warn} borderStyle="double" flexDirection="column" paddingX={1}>
      <Text bold color={t.color.warn}>
        ⚠ approval required · {req.description}
      </Text>

      <Box flexDirection="column" paddingLeft={1}>
        {shown.map((line, i) => (
          <Text color={t.color.text} key={i} wrap="truncate-end">
            {line || ' '}
          </Text>
        ))}

        {overflow > 0 ? (
          <Text color={t.color.muted}>
            … +{overflow} more line{overflow === 1 ? '' : 's'} (full text above)
          </Text>
        ) : null}
      </Box>

      <Text />

      {OPTS.map((o, i) => (
        <Text key={o}>
          <Text bold={sel === i} color={sel === i ? t.color.warn : t.color.muted} inverse={sel === i}>
            {sel === i ? '▸ ' : '  '}
            {i + 1}. {LABELS[o]}
          </Text>
        </Text>
      ))}

      <Text color={t.color.muted}>↑/↓ select · Enter confirm · 1-4 quick pick · Esc/Ctrl+C deny</Text>
    </Box>
  )
}

export function ClarifyPrompt({ cols = 80, onAnswer, onCancel, req, t }: ClarifyPromptProps) {
  const [sel, setSel] = useState(0)
  const [custom, setCustom] = useState('')
  const [typing, setTyping] = useState(false)
  const choices = req.choices ?? []

  const heading = (
    <Text bold>
      <Text color={t.color.accent}>ask</Text>
      <Text color={t.color.text}> {req.question}</Text>
    </Text>
  )

  useInput((ch, key) => {
    if (key.escape) {
      typing && choices.length ? setTyping(false) : onCancel()

      return
    }

    if (typing || !choices.length) {
      return
    }

    if (key.upArrow && sel > 0) {
      setSel(s => s - 1)
    }

    if (key.downArrow && sel < choices.length) {
      setSel(s => s + 1)
    }

    if (key.return) {
      sel === choices.length ? setTyping(true) : choices[sel] && onAnswer(choices[sel]!)
    }

    const n = parseInt(ch)

    if (n >= 1 && n <= choices.length) {
      onAnswer(choices[n - 1]!)
    }
  })

  if (typing || !choices.length) {
    return (
      <Box flexDirection="column">
        {heading}

        <Box>
          <Text color={t.color.label}>{'> '}</Text>
          <TextInput columns={Math.max(20, cols - 6)} onChange={setCustom} onSubmit={onAnswer} value={custom} />
        </Box>

        <Text color={t.color.muted}>
          Enter send · Esc {choices.length ? 'back' : 'cancel'} ·{' '}
          {isMac ? 'Cmd+C copy · Cmd+V paste · Ctrl+C cancel' : 'Ctrl+C cancel'}
        </Text>
      </Box>
    )
  }

  return (
    <Box flexDirection="column">
      {heading}

      {[...choices, 'Other (type your answer)'].map((c, i) => (
        <Text key={c}>
          <Text bold={sel === i} color={sel === i ? t.color.accent : t.color.text} inverse={sel === i}>
            {sel === i ? '▸ ' : '  '}
            {i + 1}. {c}
          </Text>
        </Text>
      ))}

      <Text color={t.color.muted}>
        ↑/↓ · Enter select · 1-{choices.length} quick pick · Esc cancel ·{' '}
        {isMac ? 'Cmd+C copy · Cmd+V paste' : 'Ctrl+C cancel'}
      </Text>
    </Box>
  )
}

export function ConfirmPrompt({ onCancel, onConfirm, req, t }: ConfirmPromptProps) {
  useInput((ch, key) => {
    if (key.return) {
      onConfirm()
    }

    if (key.escape) {
      onCancel()
    }
  })

  return (
    <Box borderColor={t.color.warn} borderStyle="round" flexDirection="column" paddingX={1}>
      <Text bold color={t.color.warn}>
        ⚠ {req.message}
      </Text>

      <Text color={t.color.muted}>Enter confirm · Esc cancel</Text>
    </Box>
  )
}

interface ApprovalPromptProps {
  onChoice: (choice: string) => void
  req: ApprovalReq
  t: Theme
}

interface ClarifyPromptProps {
  cols?: number
  onAnswer: (answer: string) => void
  onCancel: () => void
  req: ClarifyReq
  t: Theme
}

interface ConfirmPromptProps {
  onCancel: () => void
  onConfirm: () => void
  req: ConfirmReq
  t: Theme
}
