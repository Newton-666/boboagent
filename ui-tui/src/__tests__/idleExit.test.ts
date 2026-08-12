/**
 * TICKET-ENG2 (b①): idleExit 闲置退出逻辑单元测试。
 * 用 fake timers 验证：超时触发 / 活动重置 / 提前提醒 / env 解析 / 禁用。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { IdleExitTracker, idleTimeoutMinutesFromEnv } from '../lib/idleExit.js'

describe('IdleExitTracker', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('超时后触发 onIdleExit', () => {
    const tracker = new IdleExitTracker()
    const onIdleExit = vi.fn()
    const onWarn = vi.fn()
    tracker.start({ timeoutMinutes: 1, onIdleExit, onWarn, warnBeforeMinutes: 0, tickMs: 1000 })

    vi.advanceTimersByTime(61_000) // 超 1 分钟
    expect(onIdleExit).toHaveBeenCalledTimes(1)
    expect(onWarn).not.toHaveBeenCalled() // warnBefore=0 关闭提前提醒

    tracker.stop()
  })

  it('活动 poke 重置计时，不触发超时', () => {
    const tracker = new IdleExitTracker()
    const onIdleExit = vi.fn()
    tracker.start({ timeoutMinutes: 1, onIdleExit, tickMs: 1000 })

    vi.advanceTimersByTime(59_000)
    tracker.poke() // 活动
    vi.advanceTimersByTime(59_000)
    expect(onIdleExit).not.toHaveBeenCalled()

    vi.advanceTimersByTime(2_000) // 超 1 分钟
    expect(onIdleExit).toHaveBeenCalledTimes(1)

    tracker.stop()
  })

  it('超时前 warnBefore 提前提醒一次', () => {
    const tracker = new IdleExitTracker()
    const onIdleExit = vi.fn()
    const onWarn = vi.fn()
    tracker.start({
      timeoutMinutes: 2, onIdleExit, onWarn, warnBeforeMinutes: 1, tickMs: 1000
    })

    vi.advanceTimersByTime(61_000) // 剩余 59s < 60s 提醒阈值
    expect(onWarn).toHaveBeenCalledTimes(1)
    expect(onWarn).toHaveBeenCalledWith(1)

    vi.advanceTimersByTime(60_000) // 超 2 分钟
    expect(onIdleExit).toHaveBeenCalledTimes(1)

    tracker.stop()
  })

  it('timeoutMinutes=0 禁用（不启动定时器）', () => {
    const tracker = new IdleExitTracker()
    const onIdleExit = vi.fn()
    tracker.start({ timeoutMinutes: 0, onIdleExit, tickMs: 1000 })

    vi.advanceTimersByTime(120_000)
    expect(onIdleExit).not.toHaveBeenCalled()

    tracker.stop()
  })

  it('start 幂等：重复 start 重置计时', () => {
    const tracker = new IdleExitTracker()
    const onIdleExit = vi.fn()
    tracker.start({ timeoutMinutes: 1, onIdleExit, tickMs: 1000 })

    vi.advanceTimersByTime(59_000)
    tracker.start({ timeoutMinutes: 1, onIdleExit, tickMs: 1000 }) // 重启计时
    vi.advanceTimersByTime(59_000)
    expect(onIdleExit).not.toHaveBeenCalled()

    vi.advanceTimersByTime(2_000)
    expect(onIdleExit).toHaveBeenCalledTimes(1)

    tracker.stop()
  })

  it('pokeForTest 模拟长时间无活动', () => {
    const tracker = new IdleExitTracker()
    const onIdleExit = vi.fn()
    tracker.start({ timeoutMinutes: 30, onIdleExit, tickMs: 1000 })

    tracker.pokeForTest(31 * 60_000) // 模拟闲置 31 分钟
    vi.advanceTimersByTime(1000) // 下一个 tick
    expect(onIdleExit).toHaveBeenCalledTimes(1)

    tracker.stop()
  })
})

describe('idleTimeoutMinutesFromEnv', () => {
  it('默认 30', () => {
    expect(idleTimeoutMinutesFromEnv({})).toBe(30)
  })

  it('读取 BOBO_TUI_IDLE_TIMEOUT_MINUTES', () => {
    expect(idleTimeoutMinutesFromEnv({ BOBO_TUI_IDLE_TIMEOUT_MINUTES: '5' })).toBe(5)
    expect(idleTimeoutMinutesFromEnv({ BOBO_TUI_IDLE_TIMEOUT_MINUTES: '0.1' })).toBeCloseTo(0.1)
  })

  it('0 = 禁用', () => {
    expect(idleTimeoutMinutesFromEnv({ BOBO_TUI_IDLE_TIMEOUT_MINUTES: '0' })).toBe(0)
  })

  it('非法值回退默认 30', () => {
    expect(idleTimeoutMinutesFromEnv({ BOBO_TUI_IDLE_TIMEOUT_MINUTES: 'abc' })).toBe(30)
    expect(idleTimeoutMinutesFromEnv({ BOBO_TUI_IDLE_TIMEOUT_MINUTES: '-5' })).toBe(30)
  })
})
