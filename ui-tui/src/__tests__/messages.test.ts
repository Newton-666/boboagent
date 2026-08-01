import { renderSync } from '@hermes/ink'
import React from 'react'
import { PassThrough } from 'stream'
import { describe, expect, it } from 'vitest'

import { MessageLine } from '../components/messageLine.js'
import { toTranscriptMessages } from '../domain/messages.js'
import { upsert } from '../lib/messages.js'
import { stripAnsi } from '../lib/text.js'
import { DEFAULT_THEME } from '../theme.js'

describe('toTranscriptMessages', () => {
  it('preserves assistant tool-call rows so resume does not drop prior turns', () => {
    const rows = [
      { role: 'user', text: 'first prompt' },
      { role: 'tool', context: 'repo', name: 'search_files', text: 'ignored raw result' },
      { role: 'assistant', text: 'first answer' },
      { role: 'user', text: 'second prompt' }
    ]

    expect(toTranscriptMessages(rows).map(msg => [msg.role, msg.text])).toEqual([
      ['user', 'first prompt'],
      ['assistant', 'first answer'],
      ['user', 'second prompt']
    ])
    expect(toTranscriptMessages(rows)[1]?.tools?.[0]).toContain('Search Files')
  })

  // 票 TICKET-022：内部 system 消息过滤——不对 TUI 用户可见
  describe('internal system message filtering', () => {
    const internalPrefixes = [
      '[工作锚点 · 压缩豁免 · 每轮更新]\n当前任务：...',
      '[阶段完成摘要]\n已完成压缩...',
      '⚠️ 历史已压缩。若对早前工作有疑问，先翻阅上方关联笔记再作答。',
      '【上下文自查协议】当你无法确定本会话之前做过什么...',
      '[最近读过的文件]:\n  /path/to/file.py...',
      '[已注册的自定义 API]:\n  github: ...',
      '[项目规则 (AGENTS.md)]:\n  ...',
      '📝 本会话已产出笔记 3 篇...',
      '注意：这个任务涉及多个步骤或文件。\n选项 A...',
      '注意：检测到多步任务但未建台账，task_ledger...',
      '翻阅纪律：笔记按需单篇读取（read_local_file），禁止无目标批量遍历 library。',
      '[对话历史摘要]:\n  ...',
      '[Bobo 注意到] 我观察到你最近...',
      '[验证] 你声称完成了操作...',
      '## 可用的项目标准（当前未命中，以下仅供参考）',
    ]

    it('filters all known internal system prefixes from transcript', () => {
      const rows = internalPrefixes.map(text => ({ role: 'system' as const, text }))
      const result = toTranscriptMessages(rows)

      expect(result).toHaveLength(0)
    })

    it('does not filter legitimate system messages', () => {
      const rows = [
        { role: 'system' as const, text: '系统维护通知：今晚 22:00 进行升级' },
        { role: 'system' as const, text: '这是一条正常的系统消息' },
      ]
      const result = toTranscriptMessages(rows)

      expect(result).toHaveLength(2)
      expect(result[0]!.text).toContain('系统维护通知')
      expect(result[1]!.text).toContain('正常的系统消息')
    })

    it('introMsg system with empty text passes through (then trimmed)', () => {
      // introMsg has text: '' — it would be trimmed by the !text.trim() check anyway
      const rows = [
        { role: 'user' as const, text: 'hello' },
        { role: 'system' as const, text: '' },
      ]
      const result = toTranscriptMessages(rows)

      // empty text system message is skipped by !text.trim() check—not by prefix filter
      // but the important thing is it doesn't crash on empty text
      expect(result).toHaveLength(1)
      expect(result[0]!.role).toBe('user')
    })

    it('mixed legitimate and internal system messages', () => {
      const rows = [
        { role: 'user' as const, text: 'hi' },
        { role: 'system' as const, text: '[工作锚点 · 压缩豁免 · 每轮更新]\n当前任务：修复 bug' },
        { role: 'assistant' as const, text: '收到，开始修复' },
        { role: 'system' as const, text: '系统提示：您的会话将在 5 分钟后过期' },
        { role: 'user' as const, text: '继续' },
        { role: 'system' as const, text: '⚠️ 历史已压缩。若对早前工作有疑问...' },
      ]

      const result = toTranscriptMessages(rows)

      expect(result).toHaveLength(4)
      expect(result.map(m => m.role)).toEqual(['user', 'assistant', 'system', 'user'])
      expect(result[2]!.text).toContain('系统提示')
    })
  })
})

describe('MessageLine', () => {
  it('preserves a separator after compound user prompt glyphs in transcript rows', () => {
    const stdout = new PassThrough()
    const stdin = new PassThrough()
    const stderr = new PassThrough()
    let output = ''

    Object.assign(stdout, { columns: 80, isTTY: false, rows: 24 })
    Object.assign(stdin, { isTTY: false })
    Object.assign(stderr, { isTTY: false })
    stdout.on('data', chunk => {
      output += chunk.toString()
    })

    const t = {
      ...DEFAULT_THEME,
      brand: { ...DEFAULT_THEME.brand, prompt: 'Ψ >' }
    }

    const instance = renderSync(
      React.createElement(MessageLine, {
        cols: 80,
        msg: { role: 'user', text: 'Okay' },
        t
      }),
      {
        patchConsole: false,
        stderr: stderr as NodeJS.WriteStream,
        stdin: stdin as NodeJS.ReadStream,
        stdout: stdout as NodeJS.WriteStream
      }
    )

    instance.unmount()
    instance.cleanup()

    const renderedLine = stripAnsi(output)
      .split('\n')
      .find(line => line.includes('Okay'))

    expect(renderedLine).toContain('Ψ > Okay')
  })
})

describe('upsert', () => {
  it('appends when last role differs', () => {
    expect(upsert([{ role: 'user', text: 'hi' }], 'assistant', 'hello')).toHaveLength(2)
  })

  it('replaces when last role matches', () => {
    expect(upsert([{ role: 'assistant', text: 'partial' }], 'assistant', 'full')[0]!.text).toBe('full')
  })

  it('appends to empty', () => {
    expect(upsert([], 'user', 'first')).toEqual([{ role: 'user', text: 'first' }])
  })

  it('does not mutate', () => {
    const prev = [{ role: 'user' as const, text: 'hi' }]
    upsert(prev, 'assistant', 'yo')
    expect(prev).toHaveLength(1)
  })
})
