import { describe, expect, it, vi } from 'vitest'

import {
  applyVoiceRecordResponse,
  ctrlCDecision,
  escTail,
  escTopTarget,
  shouldFallThroughForScroll
} from '../app/useInputHandlers.js'
import type { OverlayState } from '../app/interfaces.js'

const baseKey = {
  downArrow: false,
  pageDown: false,
  pageUp: false,
  shift: false,
  upArrow: false,
  wheelDown: false,
  wheelUp: false
}

const baseOverlay = (): OverlayState => ({
  agents: false,
  agentsInitialHistoryIndex: 0,
  approval: null,
  clarify: null,
  clarifyTyping: false,
  confirm: null,
  modelPicker: false,
  pager: null,
  pluginsHub: false,
  scanPicker: false,
  secret: null,
  sessions: false,
  skillsHub: false,
  sudo: null
})

describe('shouldFallThroughForScroll — keep transcript scrolling alive during prompt overlays', () => {
  it('falls through for wheel scrolls', () => {
    expect(shouldFallThroughForScroll({ ...baseKey, wheelUp: true })).toBe(true)
    expect(shouldFallThroughForScroll({ ...baseKey, wheelDown: true })).toBe(true)
  })

  it('falls through for PageUp / PageDown', () => {
    expect(shouldFallThroughForScroll({ ...baseKey, pageUp: true })).toBe(true)
    expect(shouldFallThroughForScroll({ ...baseKey, pageDown: true })).toBe(true)
  })

  it('falls through for Shift+ArrowUp / Shift+ArrowDown', () => {
    expect(shouldFallThroughForScroll({ ...baseKey, shift: true, upArrow: true })).toBe(true)
    expect(shouldFallThroughForScroll({ ...baseKey, shift: true, downArrow: true })).toBe(true)
  })

  it('does NOT fall through for plain arrows — those drive in-prompt selection', () => {
    expect(shouldFallThroughForScroll({ ...baseKey, upArrow: true })).toBe(false)
    expect(shouldFallThroughForScroll({ ...baseKey, downArrow: true })).toBe(false)
  })

  it('does NOT fall through for plain Shift — without an arrow it is a no-op', () => {
    expect(shouldFallThroughForScroll({ ...baseKey, shift: true })).toBe(false)
  })

  it('does NOT fall through for unrelated state (no scroll keys held)', () => {
    expect(shouldFallThroughForScroll(baseKey)).toBe(false)
  })
})

describe('applyVoiceRecordResponse', () => {
  it('reverts optimistic REC state when the gateway reports voice busy', () => {
    const setProcessing = vi.fn()
    const setRecording = vi.fn()
    const sys = vi.fn()

    applyVoiceRecordResponse({ status: 'busy' }, true, { setProcessing, setRecording }, sys)

    expect(setRecording).toHaveBeenCalledWith(false)
    expect(setProcessing).toHaveBeenCalledWith(true)
    expect(sys).toHaveBeenCalledWith('voice: still transcribing; try again shortly')
  })

  it('keeps optimistic REC state for successful recording starts', () => {
    const setProcessing = vi.fn()
    const setRecording = vi.fn()

    applyVoiceRecordResponse({ status: 'recording' }, true, { setProcessing, setRecording }, vi.fn())

    expect(setRecording).not.toHaveBeenCalled()
    expect(setProcessing).not.toHaveBeenCalled()
  })

  it('reverts optimistic REC state when the gateway returns null', () => {
    const setProcessing = vi.fn()
    const setRecording = vi.fn()

    applyVoiceRecordResponse(null, true, { setProcessing, setRecording }, vi.fn())

    expect(setRecording).toHaveBeenCalledWith(false)
    expect(setProcessing).toHaveBeenCalledWith(false)
  })
})

describe('escTopTarget — 票 AUTO-E E-2 ESC 焦点栈优先级链', () => {
  it('approval overlay 在场 → approval（deny，不触发 interruptTurn）', () => {
    const overlay = { ...baseOverlay(), approval: { command: 'rm -rf /', description: 'danger' } }

    expect(escTopTarget(overlay)).toEqual({ kind: 'approval' })
  })

  it('clarify overlay 在场 → clarify（含 typing 输入态，ESC 回退选择而非取消）', () => {
    const overlay = { ...baseOverlay(), clarify: { choices: ['A', 'B'], question: 'pick', requestId: 'r1' } }

    expect(escTopTarget(overlay)).toEqual({ kind: 'clarify' })
    expect(overlay.clarifyTyping).toBe(false)
  })

  it('confirm overlay 在场 → confirm', () => {
    const overlay = { ...baseOverlay(), confirm: { onConfirm: () => {}, title: 'clear?' } }

    expect(escTopTarget(overlay)).toEqual({ kind: 'confirm' })
  })

  it('pager 在场 → pager', () => {
    const overlay = { ...baseOverlay(), pager: { lines: ['a'], offset: 0 } }

    expect(escTopTarget(overlay)).toEqual({ kind: 'pager' })
  })

  it('常驻面板 sessions/sudo/secret → panel（全局关闭）', () => {
    expect(escTopTarget({ ...baseOverlay(), sessions: true })).toEqual({ kind: 'panel' })
    expect(escTopTarget({ ...baseOverlay(), sudo: { prompt: 'sudo', requestId: 'r' } })).toEqual({ kind: 'panel' })
    expect(escTopTarget({ ...baseOverlay(), secret: { envVar: 'K', prompt: 'k', requestId: 'r' } })).toEqual({ kind: 'panel' })
  })

  it('modelPicker/skillsHub/pluginsHub/agents → componentOwned（组件级处理，全局跳过避免双处理）', () => {
    expect(escTopTarget({ ...baseOverlay(), modelPicker: true })).toEqual({ kind: 'componentOwned' })
    expect(escTopTarget({ ...baseOverlay(), skillsHub: true })).toEqual({ kind: 'componentOwned' })
    expect(escTopTarget({ ...baseOverlay(), pluginsHub: true })).toEqual({ kind: 'componentOwned' })
    expect(escTopTarget({ ...baseOverlay(), agents: true })).toEqual({ kind: 'componentOwned' })
  })

  it('无活跃层 → none', () => {
    expect(escTopTarget(baseOverlay())).toEqual({ kind: 'none' })
  })
})

describe('escTail — 票 AUTO-E E-2 无活跃层时 busy 中断 / idle 无操作', () => {
  it('busy（引擎跑活中）无 overlay → interruptTurn', () => {
    expect(escTail({ kind: 'none' }, true, 's1')).toBe('interrupt')
  })

  it('idle 无 overlay → noop（绝不清空 composer）', () => {
    expect(escTail({ kind: 'none' }, false, 's1')).toBe('noop')
    expect(escTail({ kind: 'none' }, false, '')).toBe('noop')
  })

  it('overlay 在场（approval 等）→ 不触发 interruptTurn（noop，由焦点栈处理）', () => {
    expect(escTail({ kind: 'approval' }, true, 's1')).toBe('noop')
    expect(escTail({ kind: 'clarify' }, true, 's1')).toBe('noop')
    expect(escTail({ kind: 'componentOwned' }, true, 's1')).toBe('noop')
  })
})

describe('ctrlCDecision — 票 AUTO-E E-3 Ctrl+C 三态钉死', () => {
  it('busy → interrupt（中断归中断）', () => {
    expect(ctrlCDecision(true, true)).toBe('interrupt')
    expect(ctrlCDecision(true, false)).toBe('interrupt')
  })

  it('非 busy 有输入 → clearInput', () => {
    expect(ctrlCDecision(false, true)).toBe('clearInput')
  })

  it('非 busy 无输入 → die（退出归退出）', () => {
    expect(ctrlCDecision(false, false)).toBe('die')
  })
})
