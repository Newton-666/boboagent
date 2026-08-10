import { Box, Text, useInput, useStdout } from '@hermes/ink'
import { useEffect, useMemo, useState } from 'react'

import { useGateway } from '../app/gatewayContext.js'
import type { SlashExecResponse } from '../gatewayTypes.js'
import { asRpcResult, rpcErrorMessage } from '../lib/rpc.js'
import type { Theme } from '../theme.js'

import { OverlayHint, useOverlayKeys, windowItems } from './overlayControls.js'

const VISIBLE = 8
const MIN_WIDTH = 40
const MAX_WIDTH = 70

/** 端点 kind → 展示名。当前后端只产 bobo/pi；Claude/Kimi 为预留（未来后端
 *  scan 支持后自动出现，无需改前端）。 */
const KIND_LABELS: Record<string, string> = {
  BOBO: 'BOBO',
  CLAUDE: 'Claude',
  KIMI: 'Kimi',
  PI: 'PI'
}

export interface ScanCandidate {
  kind: string
  n: number
  pane: string
}

/** 解析后端 /scan 输出：
 *  "1. [BOBO] <pane>\n   工作目录: …\n   启动时间: …"  → {n, kind, pane} */
export const parseCandidates = (output: string): ScanCandidate[] => {
  const out: ScanCandidate[] = []
  const re = /^\s*(\d+)\.\s*\[([A-Z]+)\]\s+(\S+)/gm
  let m: RegExpExecArray | null

  while ((m = re.exec(output))) {
    out.push({ kind: m[2]!, n: Number(m[1]), pane: m[3]! })
  }

  return out
}

export function ScanPicker({ onCancel, onConnect, sessionId, t }: ScanPickerProps) {
  const { gw } = useGateway()
  const [cands, setCands] = useState<ScanCandidate[]>([])
  const [connecting, setConnecting] = useState(false)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(true)
  const [idx, setIdx] = useState(0)

  const { stdout } = useStdout()
  const width = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, (stdout?.columns ?? 80) - 6))

  useEffect(() => {
    gw.request<SlashExecResponse>('slash.exec', { command: 'scan', session_id: sessionId ?? '' })
      .then(raw => {
        const r = asRpcResult<SlashExecResponse>(raw)

        if (!r) {
          setErr('invalid response: scan')
          setLoading(false)

          return
        }

        setCands(parseCandidates(r.output ?? ''))
        setLoading(false)
      })
      .catch((e: unknown) => {
        setErr(rpcErrorMessage(e))
        setLoading(false)
      })
  }, [gw, sessionId])

  useOverlayKeys({ onBack: onCancel, onClose: onCancel })

  useInput((_ch, key) => {
    if (connecting) {
      return
    }

    if (key.upArrow && idx > 0) {
      setIdx(v => v - 1)

      return
    }

    if (key.downArrow && idx < cands.length - 1) {
      setIdx(v => v + 1)

      return
    }

    if (key.return && cands[idx]) {
      // 选中即连：自动 /connect <编号>（轮数交给后端 L4-1 自主评估）
      setConnecting(true)
      onConnect(cands[idx]!.n)

      return
    }
  })

  const { items, offset } = useMemo(() => windowItems(cands, idx, VISIBLE), [cands, idx])

  if (loading) {
    return (
      <Box flexDirection="column" width={width}>
        <Text color={t.color.muted}>scanning tmux for peers…</Text>
        <OverlayHint t={t}>Esc cancel</OverlayHint>
      </Box>
    )
  }

  if (err) {
    return (
      <Box flexDirection="column" width={width}>
        <Text color={t.color.label}>error: {err}</Text>
        <OverlayHint t={t}>Esc/q cancel</OverlayHint>
      </Box>
    )
  }

  if (!cands.length) {
    return (
      <Box flexDirection="column" width={width}>
        <Text color={t.color.muted}>no peers found (run /scan in tmux? none alive)</Text>
        <OverlayHint t={t}>Esc/q cancel</OverlayHint>
      </Box>
    )
  }

  return (
    <Box flexDirection="column" width={width}>
      <Text bold color={t.color.accent} wrap="truncate-end">
        Select peer to connect
      </Text>

      <Text color={t.color.muted} wrap="truncate-end">
        {' '}
      </Text>

      {items.map((c, i) => {
        const active = offset + i === idx
        const label = KIND_LABELS[c.kind] ?? c.kind

        return (
          <Box key={c.n} flexDirection="row" width="100%">
            <Box backgroundColor={active ? t.color.completionCurrentBg : undefined} flexShrink={0}>
              <Text bold color={active ? t.color.label : t.color.muted}>
                {' '}
                {active ? '▸ ' : '  '}
                {c.n}.
              </Text>
            </Box>
            <Box backgroundColor={active ? t.color.completionCurrentBg : undefined}>
              <Text color={active ? t.color.text : t.color.muted} wrap="truncate-end">
                {' '}
                [{label}] {c.pane}
              </Text>
            </Box>
          </Box>
        )
      })}

      <Text color={t.color.muted} wrap="truncate-end">
        {' '}
      </Text>

      {connecting ? (
        <Text color={t.color.muted} wrap="truncate-end">
          connecting…
        </Text>
      ) : (
        <OverlayHint t={t}>
          {`↑/↓ select · Enter connect · Esc/q cancel${cands.length > VISIBLE ? ` (${idx + 1}/${cands.length})` : ''}`}
        </OverlayHint>
      )}
    </Box>
  )
}

interface ScanPickerProps {
  onCancel: () => void
  onConnect: (index: number) => void
  sessionId: null | string
  t: Theme
}
