/**
 * TICKET-ENG2 (b①): 闲置自动退出 —— 防僵尸前端机制（治本）。
 *
 * 背景：2026-08-12 22:59 六连发=5 个旧 office tmux 会话的僵尸前端集体重连风暴，
 * 内存飙升触发 macOS jetsam 击杀 owner 活跃前端。gateway 侧已有 60s 无重连退出，
 * 缺的是前端侧闲置退出 —— 本模块补齐：TUI 前端 N 分钟（默认 30，可调）无任何
 * 输入/后端活动时自动退出并清理终端模式。
 *
 * 活动信号（调用 poke()）：
 *   - 输入：useInputHandlers 的 useInput 回调（任何按键）
 *   - 后端活动：entry.tsx 里 gw.on('event', ...)（任何 gateway 事件）
 *
 * 超时前 1 分钟（warnBeforeMinutes）回调 onWarn，提示"已闲置 N 分钟，即将退出"；
 * 用户此时输入任意键即重置计时。
 */

export interface IdleExitOptions {
  /** 闲置超时（分钟）。0 = 禁用（CI/测试可设 0 关闭）。默认 30。 */
  timeoutMinutes: number
  /** 超时回调：必须走终端清理退出路径（resetTerminalModes + gw.kill + exit）。 */
  onIdleExit: () => void
  /** 超时前提醒回调（分钟余量）。 */
  onWarn?: (minutesLeft: number) => void
  /** 提前提醒的余量（分钟），默认 1。 */
  warnBeforeMinutes?: number
  /** 检查间隔 ms。默认 10_000（10s）；测试可缩短。 */
  tickMs?: number
}

export class IdleExitTracker {
  private lastActivity = Date.now()
  private timer: ReturnType<typeof setInterval> | null = null
  private warned = false
  private opts: IdleExitOptions | null = null

  /** 启动跟踪（幂等：重复调用先 stop 再 start）。 */
  start(opts: IdleExitOptions): void {
    this.stop()
    this.opts = opts
    this.lastActivity = Date.now()
    this.warned = false
    if (opts.timeoutMinutes <= 0) {
      return // 禁用
    }
    this.timer = setInterval(() => this.check(), opts.tickMs ?? 10_000)
    this.timer.unref?.()
  }

  stop(): void {
    if (this.timer) {
      clearInterval(this.timer)
      this.timer = null
    }
    this.opts = null
  }

  /** 活动信号：输入或后端事件发生时调用，重置闲置计时。 */
  poke(): void {
    this.lastActivity = Date.now()
    this.warned = false
  }

  /** 仅供测试：注入"最后活动时间"以模拟长时间无活动。 */
  pokeForTest(millisAgo: number): void {
    this.lastActivity = Date.now() - millisAgo
    this.warned = false
  }

  private check(): void {
    const opts = this.opts
    if (!opts) return
    const timeoutMs = opts.timeoutMinutes * 60_000
    const warnMs = (opts.warnBeforeMinutes ?? 1) * 60_000
    const idleMs = Date.now() - this.lastActivity

    if (idleMs >= timeoutMs) {
      // 超时：停止检查（防重复触发），走清理退出路径
      this.stop()
      opts.onIdleExit()
      return
    }
    if (!this.warned && warnMs > 0 && idleMs >= timeoutMs - warnMs) {
      this.warned = true
      opts.onWarn?.(Math.max(1, Math.ceil((timeoutMs - idleMs) / 60_000)))
    }
  }
}

/** 全局单例：entry.tsx 初始化，输入/后端事件 poke。 */
export const idleExit = new IdleExitTracker()

/** 读取 BOBO_TUI_IDLE_TIMEOUT_MINUTES（默认 30，0=禁用）。 */
export function idleTimeoutMinutesFromEnv(env: NodeJS.ProcessEnv = process.env): number {
  const raw = env.BOBO_TUI_IDLE_TIMEOUT_MINUTES
  if (raw === undefined || raw === '') {
    return 30
  }
  const n = Number(raw)
  if (!Number.isFinite(n) || n < 0) {
    return 30
  }
  return n
}
