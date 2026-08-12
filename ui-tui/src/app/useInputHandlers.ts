import { forceRedraw, useInput } from '@hermes/ink'
import { useStore } from '@nanostores/react'
import { useEffect, useRef } from 'react'

import { TYPING_IDLE_MS } from '../config/timing.js'
import type {
  ApprovalRespondResponse,
  ConfigSetResponse,
  SecretRespondResponse,
  SudoRespondResponse,
  VoiceRecordResponse
} from '../gatewayTypes.js'
import { isAction, isCopyShortcut, isMac, isVoiceToggleKey } from '../lib/platform.js'
import { idleExit } from '../lib/idleExit.js'
import { computePrecisionWheelStep, initPrecisionWheel } from '../lib/precisionWheel.js'
import { computeWheelStep, initWheelAccelForHost } from '../lib/wheelAccel.js'

import { getInputSelection } from './inputSelectionStore.js'
import type { InputHandlerContext, InputHandlerResult, OverlayState } from './interfaces.js'
import { $isBlocked, $overlayState, patchOverlayState } from './overlayStore.js'
import { turnController } from './turnController.js'
import { patchTurnState } from './turnStore.js'
import { getUiState, patchUiState } from './uiStore.js'

const isCtrl = (key: { ctrl: boolean }, ch: string, target: string) => key.ctrl && ch.toLowerCase() === target

/**
 * Approval / clarify / confirm overlays mount their own `useInput` handlers
 * for the in-prompt keys (arrows, numbers, Enter, sometimes Esc).  The global
 * input handler used to early-return for any other key while one of those
 * overlays was up, which silently disabled transcript scrolling — the user
 * couldn't read context above the prompt that the prompt itself was asking
 * about.  Returns true when the key is a transcript-scroll input that should
 * fall through to the global scroll handlers even while a prompt is active.
 *
 * Modifier-held wheel (precision mode) is included — a user who wants to
 * scroll a single line at a time during a prompt expects it to work.
 */
export function shouldFallThroughForScroll(key: {
  downArrow: boolean
  pageDown: boolean
  pageUp: boolean
  shift: boolean
  upArrow: boolean
  wheelDown: boolean
  wheelUp: boolean
}): boolean {
  if (key.wheelUp || key.wheelDown) {
    return true
  }

  if (key.pageUp || key.pageDown) {
    return true
  }

  if (key.shift && (key.upArrow || key.downArrow)) {
    return true
  }

  return false
}

/**
 * 票 AUTO-E E-2：ESC 焦点栈判定（纯函数，测试钉死）。
 * 与 useInput 里 ESC 单一入口的 3-4 层一一对应：
 *   approval > clarify > confirm > pager（最顶层 prompt overlay）
 *   > panel（sessions/sudo/secret，全局关闭）
 *   > componentOwned（modelPicker/skillsHub/pluginsHub/agents —— 组件级
 *     useInput 处理，内部 mode/stage/filter 内聚，全局跳过避免双处理）
 *   > none（无活跃层 → 调用方决定 busy 中断 / idle 无操作）
 */
export type EscTopTarget =
  | { kind: 'approval' }
  | { kind: 'clarify' }
  | { kind: 'confirm' }
  | { kind: 'pager' }
  | { kind: 'panel' }
  | { kind: 'componentOwned' }
  | { kind: 'none' }

export function escTopTarget(overlay: OverlayState): EscTopTarget {
  if (overlay.approval) {
    return { kind: 'approval' }
  }

  if (overlay.clarify) {
    return { kind: 'clarify' }
  }

  if (overlay.confirm) {
    return { kind: 'confirm' }
  }

  if (overlay.pager) {
    return { kind: 'pager' }
  }

  if (overlay.sessions || overlay.sudo || overlay.secret) {
    return { kind: 'panel' }
  }

  if (overlay.modelPicker || overlay.skillsHub || overlay.pluginsHub || overlay.agents || overlay.scanPicker) {
    return { kind: 'componentOwned' }
  }

  return { kind: 'none' }
}

/**
 * 票 AUTO-E E-2：ESC 无活跃层时的兜底判定（纯函数，测试钉死）。
 * busy（引擎跑活中）→ interruptTurn；idle → 无操作（绝不清空 composer）。
 */
export const escTail = (target: EscTopTarget, busy: boolean, sid: string): 'interrupt' | 'noop' => {
  if (target.kind === 'none' && busy && sid) {
    return 'interrupt'
  }

  return 'noop'
}

/**
 * 票 AUTO-E E-3：Ctrl+C 三态判定（纯函数，测试钉死，与 v0.7 裁决一致）：
 * busy → 中断回合；有输入 → 清空输入；否则 → 退出。中断归中断、退出归退出。
 */
export const ctrlCDecision = (busy: boolean, hasInput: boolean): 'interrupt' | 'clearInput' | 'die' => {
  if (busy) {
    return 'interrupt'
  }

  if (hasInput) {
    return 'clearInput'
  }

  return 'die'
}

export function applyVoiceRecordResponse(
  response: null | VoiceRecordResponse,
  starting: boolean,
  voice: Pick<InputHandlerContext['voice'], 'setProcessing' | 'setRecording'>,
  sys: (text: string) => void
) {
  if (!starting || response?.status === 'recording') {
    return
  }

  voice.setRecording(false)

  if (response?.status === 'busy') {
    voice.setProcessing(true)
    sys('voice: still transcribing; try again shortly')
  } else {
    voice.setProcessing(false)
  }
}

// Approval 选项
const APPROVAL_OPTS = ['once', 'session', 'always', 'deny'] as const

export function useInputHandlers(ctx: InputHandlerContext): InputHandlerResult {
  const { actions, composer, gateway, terminal, voice, wheelStep } = ctx
  const { actions: cActions, refs: cRefs, state: cState } = composer

  const overlay = useStore($overlayState)
  const isBlocked = useStore($isBlocked)
  const pagerPageSize = Math.max(5, (terminal.stdout?.rows ?? 24) - 6)
  const scrollIdleTimer = useRef<null | ReturnType<typeof setTimeout>>(null)
  const approvalSelRef = useRef(0)

  // Wheel accel ported from claude-code: inter-event timing drives step size,
  // direction flips reset. wheelStep (WHEEL_SCROLL_STEP) is the base; final
  // rows = wheelStep × accelMult. State mutates in place across renders.
  const wheelAccelRef = useRef(initWheelAccelForHost())

  const precisionWheelRef = useRef(initPrecisionWheel())

  useEffect(() => () => clearTimeout(scrollIdleTimer.current ?? undefined), [])

  const scrollTranscript = (delta: number) => {
    if (getUiState().busy) {
      turnController.boostStreamingForScroll()
      clearTimeout(scrollIdleTimer.current ?? undefined)
      scrollIdleTimer.current = setTimeout(() => {
        scrollIdleTimer.current = null
        turnController.relaxStreaming()
      }, TYPING_IDLE_MS)
    }

    terminal.scrollWithSelection(delta)
  }

  const copySelection = () => {
    // ink's copySelection() already calls setClipboard() which handles
    // pbcopy (macOS), wl-copy/xclip (Linux), tmux, and OSC 52 fallback.
    terminal.selection.copySelection()
  }

  const clearSelection = () => {
    terminal.selection.clearSelection()
  }

  const cancelOverlayFromCtrlC = () => {
    if (overlay.clarify) {
      return actions.answerClarify('')
    }

    if (overlay.approval) {
      return gateway
        .rpc<ApprovalRespondResponse>('approval.respond', { choice: 'deny', session_id: getUiState().sid })
        .then(r => r && (patchOverlayState({ approval: null }), patchTurnState({ outcome: 'denied' })))
    }

    if (overlay.sudo) {
      return gateway
        .rpc<SudoRespondResponse>('sudo.respond', { password: '', request_id: overlay.sudo.requestId })
        .then(r => r && (patchOverlayState({ sudo: null }), actions.sys('sudo cancelled')))
    }

    if (overlay.secret) {
      return gateway
        .rpc<SecretRespondResponse>('secret.respond', { request_id: overlay.secret.requestId, value: '' })
        .then(r => r && (patchOverlayState({ secret: null }), actions.sys('secret entry cancelled')))
    }

    if (overlay.modelPicker) {
      return patchOverlayState({ modelPicker: false })
    }

    if (overlay.skillsHub) {
      return patchOverlayState({ skillsHub: false })
    }

    if (overlay.pluginsHub) {
      return patchOverlayState({ pluginsHub: false })
    }

    if (overlay.sessions) {
      return patchOverlayState({ sessions: false })
    }

    if (overlay.agents) {
      return patchOverlayState({ agents: false })
    }
  }

  const cycleQueue = (dir: 1 | -1) => {
    const len = cRefs.queueRef.current.length

    if (!len) {
      return false
    }

    const index = cState.queueEditIdx === null ? (dir > 0 ? 0 : len - 1) : (cState.queueEditIdx + dir + len) % len

    cActions.setQueueEdit(index)
    cActions.setHistoryIdx(null)
    cActions.setInput(cRefs.queueRef.current[index] ?? '')

    return true
  }

  const cycleHistory = (dir: 1 | -1) => {
    const h = cRefs.historyRef.current
    const cur = cState.historyIdx

    if (dir < 0) {
      if (!h.length) {
        return
      }

      if (cur === null) {
        cRefs.historyDraftRef.current = cState.input
      }

      const index = cur === null ? h.length - 1 : Math.max(0, cur - 1)

      cActions.setHistoryIdx(index)
      cActions.setQueueEdit(null)
      cActions.setInput(h[index] ?? '')

      return
    }

    if (cur === null) {
      return
    }

    const next = cur + 1

    if (next >= h.length) {
      cActions.setHistoryIdx(null)
      cActions.setInput(cRefs.historyDraftRef.current)
    } else {
      cActions.setHistoryIdx(next)
      cActions.setInput(h[next] ?? '')
    }
  }

  // CLI parity: Ctrl+B toggles a VAD-bounded push-to-talk capture
  // (NOT the voice-mode umbrella bit). The mode is enabled via /voice on;
  // Ctrl+B while the mode is off sys-nudges the user. While the mode is
  // on, the first press starts a single VAD-bounded capture
  // (gateway -> start_continuous(auto_restart=false), VAD auto-stop ->
  // transcribe -> idle), a subsequent press stops and transcribes it.
  // The gateway publishes voice.status + voice.transcript events that
  // createGatewayEventHandler turns into UI badges and composer injection.
  const voiceRecordToggle = () => {
    if (!voice.enabled) {
      return actions.sys('voice: mode is off — enable with /voice on')
    }

    const starting = !voice.recording
    const action = starting ? 'start' : 'stop'

    // Optimistic UI — flip the REC badge immediately so the user gets
    // feedback while the RPC round-trips; the voice.status event is the
    // authoritative source and may correct us.
    if (starting) {
      voice.setRecording(true)
    } else {
      voice.setRecording(false)
      voice.setProcessing(false)
    }

    gateway
      .rpc<VoiceRecordResponse>('voice.record', { action, session_id: getUiState().sid })
      .then(r => applyVoiceRecordResponse(r, starting, voice, actions.sys))
      .catch((e: Error) => {
        // Revert optimistic UI on failure.
        if (starting) {
          voice.setRecording(false)
        }

        actions.sys(`voice error: ${e.message}`)
      })
  }

  useInput((ch, key) => {
    // TICKET-ENG2 (b①): 任何按键 = 活动信号，重置闲置退出计时
    idleExit.poke()
    const live = getUiState()

    // ── 票 AUTO-E E-2：ESC 单一入口（焦点优先级链） ──
    // 1. voice 组合键（ctrl/alt/super+escape）——最高，永远响应
    // 2. 输入编辑态：queue-edit cancel > selection clear
    // 3-4. overlay 焦点栈（escTopTarget）：approval deny > clarify
    //      （typing 回退 / 取消）> confirm 关闭 > pager 关闭 > panel
    //      （sessions/sudo/secret 全局关闭）> componentOwned（组件级处理）
    // 5. 无活跃层：busy → 全局中断回合；idle → 无操作（绝不清空 composer）
    if (key.escape) {
      if (isVoiceToggleKey(key, ch, voice.recordKey)) {
        return voiceRecordToggle()
      }

      if (cState.queueEditIdx !== null) {
        return cActions.clearIn()
      }

      if (terminal.hasSelection) {
        return clearSelection()
      }

      const target = escTopTarget(overlay)

      if (target.kind === 'approval') {
        gateway
          .rpc<ApprovalRespondResponse>('approval.respond', { choice: 'deny', session_id: live.sid })
          .then(r => r && (patchOverlayState({ approval: null }), patchTurnState({ outcome: 'denied' })))
        return
      }

      if (target.kind === 'clarify') {
        // typing（自定义输入态）→ 回退到选择列表；否则取消（持久化问题+选项）
        if (overlay.clarifyTyping) {
          patchOverlayState({ clarifyTyping: false })
        } else {
          actions.answerClarify('')
        }
        return
      }

      if (target.kind === 'confirm') {
        patchOverlayState({ confirm: null })
        return
      }

      if (target.kind === 'pager') {
        patchOverlayState({ pager: null })
        return
      }

      if (target.kind === 'panel') {
        // sessions/sudo/secret：cancelOverlayFromCtrlC 内部按 sudo > secret > sessions 关闭
        cancelOverlayFromCtrlC()
        return
      }

      if (target.kind === 'componentOwned') {
        // modelPicker/skillsHub/pluginsHub/agents：组件级 useInput 处理，全局跳过
        return
      }

      // none（无活跃层）：busy → 中断；idle → 无操作（escTail 判定，测试钉死）
      if (escTail(target, Boolean(live.busy && live.sid), live.sid) === 'interrupt') {
        return turnController.interruptTurn({
          appendMessage: actions.appendMessage,
          gw: gateway.gw,
          sid: live.sid,
          sys: actions.sys
        })
      }

      return
    }

    // ── 优先处理 approval 弹窗的按键（ESC 已在上方单一入口处理）──
    if (overlay.approval) {
      if (isCtrl(key, ch, 'c')) {
        // Ctrl+C → 拒绝
        gateway
          .rpc<ApprovalRespondResponse>('approval.respond', { choice: 'deny', session_id: live.sid })
          .then(r => r && (patchOverlayState({ approval: null }), patchTurnState({ outcome: 'denied' })))
        return
      }

      // 数字键 1-4 快速选择
      const n = parseInt(ch, 10)
      if (n >= 1 && n <= 4) {
        const choice = APPROVAL_OPTS[n - 1]
        gateway
          .rpc<ApprovalRespondResponse>('approval.respond', { choice, session_id: live.sid })
          .then(r => r && (patchOverlayState({ approval: null }), patchTurnState({ outcome: `approved (${choice})` }), patchUiState({ status: 'running…' })))
        return
      }

      // 回车 → 确认当前选择
      if (key.return) {
        const choice = APPROVAL_OPTS[approvalSelRef.current]
        gateway
          .rpc<ApprovalRespondResponse>('approval.respond', { choice, session_id: live.sid })
          .then(r => r && (patchOverlayState({ approval: null }), patchTurnState({ outcome: `approved (${choice})` }), patchUiState({ status: 'running…' })))
        return
      }

      // 方向键上下 → 移动选择
      if (key.upArrow && approvalSelRef.current > 0) {
        approvalSelRef.current -= 1
        return
      }
      if (key.downArrow && approvalSelRef.current < 3) {
        approvalSelRef.current += 1
        return
      }

      // 其他按键在 approval 弹窗中不处理
      return
    }

    if (isBlocked) {
      // When approval/clarify/confirm overlays are active, their own useInput
      // handlers must receive keystrokes (arrow keys, numbers, Enter).  Only
      // intercept Ctrl+C here so the user can deny/dismiss — all other keys
      // fall through to the component-level handlers.
      //
      // Scroll inputs (wheel / PageUp / PageDown / Shift+↑↓) are special:
      // they must reach the transcript scroll handlers below even with a
      // prompt up.  Long-thread context the prompt is asking about often
      // lives above the visible viewport, and being unable to read it while
      // answering felt like the prompt had locked the entire UI.  Explicitly
      // skip the prompt-overlay early-return for scroll keys so they fall
      // through to the wheel / PageUp / Shift+arrow handlers below.
      const promptOverlay = overlay.clarify || overlay.confirm
      const fallThroughForScroll = promptOverlay && shouldFallThroughForScroll(key)

      if (promptOverlay && !fallThroughForScroll) {
        if (isCtrl(key, ch, 'c')) {
          cancelOverlayFromCtrlC()
        }
        // ESC 已由上方单一入口处理（clarify typing 回退 / 取消、confirm 关闭）

        return
      }

      if (overlay.pager) {
        if (key.escape || isCtrl(key, ch, 'c') || ch === 'q') {
          return patchOverlayState({ pager: null })
        }

        const move = (delta: number | 'top' | 'bottom') =>
          patchOverlayState(prev => {
            if (!prev.pager) {
              return prev
            }

            const { lines, offset } = prev.pager
            const max = Math.max(0, lines.length - pagerPageSize)
            const step = delta === 'top' ? -lines.length : delta === 'bottom' ? lines.length : delta
            const next = Math.max(0, Math.min(offset + step, max))

            return next === offset ? prev : { ...prev, pager: { ...prev.pager, offset: next } }
          })

        if (key.upArrow || ch === 'k') {
          return move(-1)
        }

        if (key.downArrow || ch === 'j') {
          return move(1)
        }

        if (key.pageUp || ch === 'b') {
          return move(-pagerPageSize)
        }

        if (ch === 'g') {
          return move('top')
        }

        if (ch === 'G') {
          return move('bottom')
        }

        if (key.return || ch === ' ' || key.pageDown) {
          patchOverlayState(prev => {
            if (!prev.pager) {
              return prev
            }

            const { lines, offset } = prev.pager
            const max = Math.max(0, lines.length - pagerPageSize)

            // Auto-close only when already at the last page — otherwise clamp
            // to `max` so the offset matches what the line/page-back handlers
            // can reach (prevents a snap-back jump on the next ↑/↓/PgUp).
            return offset >= max
              ? { ...prev, pager: null }
              : { ...prev, pager: { ...prev.pager, offset: Math.min(offset + pagerPageSize, max) } }
          })
        }

        return
      }

      if (isCtrl(key, ch, 'c')) {
        cancelOverlayFromCtrlC()
      }
      // ESC 已由上方单一入口处理（panel 关闭 / componentOwned 跳过）

      // When a prompt overlay is up and the user pressed a scroll key, fall
      // through to the global scroll handlers below instead of returning.
      // Otherwise nothing above this comment matched, and there's nothing
      // useful to do for an arbitrary key while blocked.
      if (!fallThroughForScroll) {
        return
      }
    }

    if (cState.completions.length && cState.input && cState.historyIdx === null && (key.upArrow || key.downArrow)) {
      const len = cState.completions.length

      cActions.setCompIdx(i => (key.upArrow ? (i - 1 + len) % len : (i + 1) % len))

      return
    }

    if (key.wheelUp || key.wheelDown) {
      const dir: -1 | 1 = key.wheelUp ? -1 : 1
      const now = Date.now()
      // Modifier-held wheel = precision mode: one row per frame, no accel.
      // Smooth mice / trackpads emit tiny same-frame bursts; coalesce those
      // without the old 80ms throttle that made opt-scroll feel stepped.
      // SGR/X10 mouse encoding only carries shift/meta/ctrl bits; Cmd on
      // macOS is intercepted by the terminal, so we honor Option (meta) on
      // Mac / Alt (meta) on Win+Linux / Ctrl as a portable fallback. Shift
      // is reserved for selection extension.
      const hasModifier = key.meta || key.ctrl
      const precision = computePrecisionWheelStep(precisionWheelRef.current, dir, hasModifier, now)

      if (precision.active) {
        // Entering precision mode must discard any accelerated wheel state;
        // otherwise the next normal wheel event inherits stale momentum.
        if (precision.entered) {
          wheelAccelRef.current = initWheelAccelForHost()
        }

        return precision.rows ? scrollTranscript(dir * wheelStep) : undefined
      }

      // 0 = direction-flip bounce deferred; skip the no-op scroll.
      const rows = computeWheelStep(wheelAccelRef.current, dir, now)

      return rows ? scrollTranscript(dir * rows * wheelStep) : undefined
    }

    if (key.shift && key.upArrow) {
      return scrollTranscript(-1)
    }

    if (key.shift && key.downArrow) {
      return scrollTranscript(1)
    }

    if (key.pageUp || key.pageDown) {
      // Half-viewport keeps 50% continuity and stays under Ink's
      // `delta < innerHeight` DECSTBM fast-path threshold.
      const viewport = terminal.scrollRef.current?.getViewportHeight() ?? Math.max(6, (terminal.stdout?.rows ?? 24) - 8)
      const step = Math.max(4, Math.floor(viewport / 2))

      return scrollTranscript(key.pageUp ? -step : step)
    }

    // Escape 相关分支已全部收敛到上方单一入口（票 AUTO-E E-2）：
    // voice 组合键 > queue-edit cancel > selection clear > overlay 焦点栈 > busy 中断 / idle 无操作。

    // Ctrl+K：清空当前输入行（终端/browser 标准行为，零学习成本）
    if ((key.ctrl || key.meta) && ch === 'k') {
      cActions.setInput('')
      return
    }

    if (key.upArrow && !cState.inputBuf.length) {
      const inputSel = getInputSelection()
      const cursor = inputSel && inputSel.start === inputSel.end ? inputSel.start : null

      const noLineAbove =
        !cState.input || (cursor !== null && cState.input.lastIndexOf('\n', Math.max(0, cursor - 1)) < 0)

      if (noLineAbove) {
        cycleQueue(1) || cycleHistory(-1)

        return
      }
    }

    if (key.downArrow && !cState.inputBuf.length) {
      const inputSel = getInputSelection()
      const cursor = inputSel && inputSel.start === inputSel.end ? inputSel.start : null
      const noLineBelow = !cState.input || (cursor !== null && cState.input.indexOf('\n', cursor) < 0)

      if (noLineBelow || cState.historyIdx !== null) {
        cycleQueue(-1) || cycleHistory(1)

        return
      }
    }

    if (isCopyShortcut(key, ch)) {
      if (terminal.hasSelection) {
        return copySelection()
      }

      const inputSel = getInputSelection()

      if (inputSel && inputSel.end > inputSel.start) {
        inputSel.clear()

        return
      }

      // On macOS, Cmd+C with no selection is a no-op (Ctrl+C below handles interrupt).
      // On non-macOS, isAction uses Ctrl, so fall through to interrupt/clear/exit.
      if (isMac) {
        return
      }
    }

    if (isCtrl(key, ch, 'x') && cState.queueEditIdx !== null) {
      cActions.removeQueue(cState.queueEditIdx)

      return cActions.clearIn()
    }

    if (isCtrl(key, ch, 'x')) {
      return patchOverlayState({ sessions: true })
    }

    if (key.ctrl && ch.toLowerCase() === 'c') {
      // 票 AUTO-E E-3：Ctrl+C 三态（ctrlCDecision 判定，测试钉死）
      const decision = ctrlCDecision(Boolean(live.busy && live.sid), Boolean(cState.input || cState.inputBuf.length))

      if (decision === 'interrupt') {
        return turnController.interruptTurn({
          appendMessage: actions.appendMessage,
          gw: gateway.gw,
          sid: live.sid,
          sys: actions.sys
        })
      }

      if (decision === 'clearInput') {
        return cActions.clearIn()
      }

      return actions.die()
    }

    if (isAction(key, ch, 'd')) {
      return actions.die()
    }

    if (isAction(key, ch, 'l')) {
      clearSelection()
      forceRedraw(terminal.stdout ?? process.stdout)

      return
    }

    if (isVoiceToggleKey(key, ch, voice.recordKey)) {
      return voiceRecordToggle()
    }

    // Cmd/Ctrl+G, plus Alt+G fallback for VSCode/Cursor (they bind the
    // primary keystroke to "Find Next" before the TUI sees it; Alt+G
    // arrives as meta+g across platforms).
    if (ch.toLowerCase() === 'g' && (isAction(key, ch, 'g') || key.meta)) {
      return void cActions.openEditor().catch((err: unknown) => {
        actions.sys(err instanceof Error ? `failed to open editor: ${err.message}` : 'failed to open editor')
      })
    }

    // shift-tab flips yolo without spending a turn (claude-code parity)
    if (key.shift && key.tab && !cState.completions.length) {
      if (!live.sid) {
        return void actions.sys('yolo needs an active session')
      }

      // gateway.rpc swallows errors with its own sys() message and resolves to null,
      // so we only speak when it came back with a real shape. null = rpc already spoke.
      return void gateway.rpc<ConfigSetResponse>('config.set', { key: 'yolo', session_id: live.sid }).then(r => {
        if (r?.value === '1') {
          return actions.sys('yolo on')
        }

        if (r?.value === '0') {
          return actions.sys('yolo off')
        }

        if (r) {
          actions.sys('failed to toggle yolo')
        }
      })
    }

    if (key.tab && cState.completions.length) {
      const row = cState.completions[cState.compIdx]

      if (row?.text) {
        const text =
          cState.input.startsWith('/') && row.text.startsWith('/') && cState.compReplace > 0
            ? row.text.slice(1)
            : row.text

        cActions.setInput(cState.input.slice(0, cState.compReplace) + text)
      }

      return
    }

    if (isAction(key, ch, 'k') && cRefs.queueRef.current.length && live.sid) {
      const next = cActions.dequeue()

      if (next) {
        cActions.setQueueEdit(null)
        actions.dispatchSubmission(next)
      }
    }
  })

  return { pagerPageSize }
}
