import { beforeEach, describe, expect, it } from 'vitest'

import { $overlayState, resetOverlayState } from '../app/overlayStore.js'
import { findSlashCommand } from '../app/slash/registry.js'
import { parseCandidates } from '../components/scanPicker.js'

describe('TICKET-SCAN-L4-2: /scan 端点选择器', () => {
  beforeEach(() => {
    resetOverlayState()
  })

  describe('parseCandidates — 后端 /scan 输出解析', () => {
    it('解析标准候选块（编号 + kind + pane）', () => {
      const out = [
        '检测到以下可对话对象：',
        '',
        '1. [BOBO] %1',
        '   工作目录: /tmp/a',
        '   启动时间: 10:00',
        '',
        '2. [PI] %2',
        '   工作目录: /tmp/b',
        '   启动时间: 10:01',
        '',
        '当前 bobo：API 直采模式 ✓（无需 tmux）',
        '',
        '连接: /connect <编号> [轮数]'
      ].join('\n')

      expect(parseCandidates(out)).toEqual([
        { kind: 'BOBO', n: 1, pane: '%1' },
        { kind: 'PI', n: 2, pane: '%2' }
      ])
    })

    it('无候选时返回空数组', () => {
      expect(parseCandidates('未发现可对话对象（tmux 内无 bobo/pi）')).toEqual([])
    })

    it('未来接 Claude/Kimi：后端加 kind 后自动解析，无需改前端', () => {
      const out = '1. [CLAUDE] %3\n2. [KIMI] %4'
      expect(parseCandidates(out)).toEqual([
        { kind: 'CLAUDE', n: 1, pane: '%3' },
        { kind: 'KIMI', n: 2, pane: '%4' }
      ])
    })

    it('多行详情（工作目录/启动时间）不影响解析', () => {
      const out = [
        '1. [BOBO] %1',
        '   工作目录: /tmp/a',
        '   启动时间: 10:00',
        '   额外字段: 不匹配',
        '2. [PI] %2',
        '   工作目录: /tmp/b'
      ].join('\n')

      expect(parseCandidates(out)).toEqual([
        { kind: 'BOBO', n: 1, pane: '%1' },
        { kind: 'PI', n: 2, pane: '%2' }
      ])
    })
  })

  describe('/scan 命令', () => {
    it('注册在前端 slash registry（本地命令）', () => {
      const cmd = findSlashCommand('scan')
      expect(cmd).toBeDefined()
      expect(cmd!.name).toBe('scan')
    })

    it('无参数执行 → 打开 scanPicker overlay', () => {
      const cmd = findSlashCommand('scan')!
      const ctx = {
        composer: {},
        flight: 0,
        gateway: {},
        guarded: (fn: (r: never) => void) => (r: never) => fn(r),
        guardedErr: () => {},
        local: {},
        session: {},
        sid: 's1',
        slashFlightRef: { current: 0 },
        stale: () => false,
        transcript: {},
        ui: {}
      } as never

      cmd.run('', ctx as never, '/scan')

      expect($overlayState.get().scanPicker).toBe(true)
    })
  })
})
