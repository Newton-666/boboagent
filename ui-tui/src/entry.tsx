#!/usr/bin/env -S node --max-old-space-size=8192 --expose-gc
import './lib/forceTruecolor.js'

import type { FrameEvent } from '@hermes/ink'

import { TERMUX_TUI_MODE } from './config/env.js'
import { GatewayClient } from './gatewayClient.js'
import { setupGracefulExit } from './lib/gracefulExit.js'
import { formatBytes, type HeapDumpResult, performHeapDump } from './lib/memory.js'
import { type MemorySnapshot, startMemoryMonitor } from './lib/memoryMonitor.js'
import { openExternalUrl } from './lib/openExternalUrl.js'
import { recordParentLifecycle } from './lib/parentLog.js'
import { resetTerminalModes } from './lib/terminalModes.js'

if (!process.stdin.isTTY) {
  console.log('bobo-tui: no TTY')
  process.exit(0)
}

resetTerminalModes()

process.on('exit', () => {
  resetTerminalModes()
})

if (TERMUX_TUI_MODE) {
  process.stdout.write('\n')
} else {
  process.stdout.write('\x1b[2J\x1b[H\x1b[3J')
}

const gw = new GatewayClient()

gw.start()

const dumpNotice = (snap: MemorySnapshot, dump: HeapDumpResult | null) =>
  `bobo-tui: ${snap.level} memory (${formatBytes(snap.heapUsed)}) — auto heap dump → ${dump?.heapPath ?? dump?.diagPath ?? '(failed)'}\n`

setupGracefulExit({
  cleanups: [
    () => {
      resetTerminalModes()
      return gw.kill('graceful-exit-cleanup')
    }
  ],
  onError: (scope, err) => {
    const message = err instanceof Error ? `${err.name}: ${err.message}\n${err.stack ?? ''}` : String(err)
    recordParentLifecycle(`${scope}: ${message.split('\n')[0]?.slice(0, 400) ?? ''}`)
    process.stderr.write(`bobo-tui lifecycle ${scope}: ${message.slice(0, 2000)}\n`)
  },
  onSignal: signal => {
    recordParentLifecycle(`graceful-exit received signal=${signal} → killing gateway`)
    resetTerminalModes()
    process.stderr.write(`bobo-tui lifecycle: received ${signal}\n`)
  }
})

const stopMemoryMonitor = startMemoryMonitor({
  onCritical: (snap, dump) => {
    recordParentLifecycle(`memory-critical process.exit(137) heap=${formatBytes(snap.heapUsed)} rss=${formatBytes(snap.rss)} dump=${dump?.heapPath ?? 'failed'}`)
    resetTerminalModes()
    process.stderr.write(`bobo-tui lifecycle: memory critical exit heap=${formatBytes(snap.heapUsed)} rss=${formatBytes(snap.rss)}\n`)
    process.stderr.write(dumpNotice(snap, dump))
    process.stderr.write('bobo-tui: exiting to avoid OOM; restart to recover\n')
    process.exit(137)
  },
  onHigh: (snap, dump) => process.stderr.write(dumpNotice(snap, dump)),
  onWarn: snap => {
    recordParentLifecycle(`memory-warning fast heap growth heap=${formatBytes(snap.heapUsed)} rss=${formatBytes(snap.rss)}`)
    process.stderr.write(
      `bobo-tui: heap climbing fast (${formatBytes(snap.heapUsed)}) — a large tool output or long session may be straining memory\n`
    )
  }
})

if (process.env.BOBO_HEAPDUMP_ON_START === '1') {
  void performHeapDump('manual')
}

process.on('beforeExit', () => stopMemoryMonitor())

const [ink, { App }, { logFrameEvent }, { trackFrame }] = await Promise.all([
  import('@hermes/ink'),
  import('./app.js'),
  import('./lib/perfPane.js'),
  import('./lib/fpsStore.js')
])

const onFrame =
  logFrameEvent || trackFrame
    ? (event: FrameEvent) => {
        logFrameEvent?.(event)
        trackFrame?.(event.durationMs)
      }
    : undefined

ink.render(<App gw={gw} />, {
  exitOnCtrlC: false,
  onFrame,
  onHyperlinkClick: url => {
    openExternalUrl(url)
  }
})
