// TICKET-GW-SOCK 专项测试：gateway-socket.cjs（纯 Node，无 electron）
'use strict'
const test = require('node:test')
const assert = require('node:assert')
const { spawn } = require('child_process')
const os = require('os')
const path = require('path')
const fs = require('fs')
const net = require('net')

const {
  resolveGwSockPath,
  probeSocket,
  cleanupStaleSocket,
  buildBackendEnv,
  createGatewayClient,
} = require('../gateway-socket.cjs')

// apps/desktop/electron/test/ 上四级 = 仓库根（Kimi 终审修复：原上三级落在 apps/，.venv 与包都找不到，后端 spawn 即 exit 1）
const ROOT = path.resolve(__dirname, '..', '..', '..', '..')
const PY =
  process.env.BOBO_PYTHON ||
  (fs.existsSync(path.join(ROOT, '.venv', 'bin', 'python'))
    ? path.join(ROOT, '.venv', 'bin', 'python')
    : 'python3')

function tmpSock(tag) {
  return path.join(os.tmpdir(), `bobo-gw-test-${tag}-${Date.now()}-${Math.random().toString(36).slice(2)}.sock`)
}

// 与 TICKET-018 同款：python -c 直调 _run_socket_backend（绕开 config/CLI 初始化）
function spawnTestBackend(sockPath) {
  // TICKET-GW-MULTI：数据目录隔离到 tmp——session.create 等写盘 handler
  // 绝不触碰真实 BOBO_DATA_DIR/会话目录（用户财产红线，2026-07-27 事故备案）
  const isoData = fs.mkdtempSync(path.join(os.tmpdir(), 'bobo-gw-test-data-'))
  const env = {
    ...process.env,
    BOBO_GW_SOCKET: sockPath,
    BOBO_GW_IDLE_TIMEOUT: '0',
    BOBO_TEST_MODE: '1',
    OBSIDIAN_VAULT: '',
    BOBO_DATA_DIR: isoData,
    BOBO_SESSION_DIR: path.join(isoData, 'sessions'),
  }
  const proc = spawn(
    PY,
    [
      '-c',
      "import os,sys; sys.path.insert(0,'.'); from bobo_tui_gateway.entry import _run_socket_backend; _run_socket_backend(os.environ['BOBO_GW_SOCKET'])",
    ],
    { cwd: ROOT, env, stdio: ['ignore', 'ignore', 'pipe'] }
  )
  let err = ''
  proc.stderr.on('data', (d) => { err += d.toString() })
  proc._err = () => err
  return proc
}

async function waitFor(fn, timeoutMs = 8000, step = 50) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (fn()) return true
    await new Promise((r) => setTimeout(r, step))
  }
  return false
}

async function waitForSocket(sockPath, proc, timeoutMs = 8000) {
  return waitFor(() => {
    if (proc && proc.exitCode !== null) return true // 提前退出也算（调用方断言 exitCode）
    return fs.existsSync(sockPath)
  }, timeoutMs)
}

test('resolveGwSockPath 固定名落在 tmpdir', () => {
  const p = resolveGwSockPath()
  assert.ok(p.startsWith(os.tmpdir()), `path=${p}`)
  assert.ok(p.endsWith('bobo-gw-main.sock'), `path=${p}`)
})

test('buildBackendEnv：显式注入 BOBO_GW_SOCKET + 空闲超时 0 + 仍删 BOBO_SESSION_DIR', () => {
  const env = buildBackendEnv({
    projectRoot: '/x',
    baseEnv: { BOBO_GW_SOCKET: 'LEAKED', BOBO_SESSION_DIR: '/tui/session', BOBO_BACKEND: '0' },
  })
  assert.strictEqual(env.BOBO_GW_SOCKET, resolveGwSockPath())
  assert.strictEqual(env.BOBO_GW_IDLE_TIMEOUT, '0')
  assert.strictEqual(env.BOBO_SESSION_DIR, undefined)
  assert.strictEqual(env.BOBO_BACKEND, '1')
  assert.strictEqual(env.PYTHONPATH, '/x')
})

test('cleanupStaleSocket 删除陈旧文件且幂等', () => {
  const p = tmpSock('stale')
  fs.writeFileSync(p, 'stale')
  cleanupStaleSocket(p)
  assert.ok(!fs.existsSync(p))
  cleanupStaleSocket(p) // 幂等不炸
})

test('probeSocket：无活跃后端 false；有活跃后端 true', async () => {
  const sockPath = tmpSock('probe')
  assert.strictEqual(await probeSocket(sockPath, 500), false)
  const srv = net.createServer(() => {})
  await new Promise((res) => srv.listen(sockPath, res))
  try {
    assert.strictEqual(await probeSocket(sockPath, 500), true)
  } finally {
    srv.close()
    cleanupStaleSocket(sockPath)
  }
})

// ready 消息实际形态：method='event' + params.type='gateway.ready'
const isReady = (m) => m.method === 'event' && m.params && m.params.type === 'gateway.ready'

test('createGatewayClient ⇄ 真实后端：连接→ready→ping→断开→后端存活→重连→ready', async (t) => {
  const sockPath = tmpSock('client')
  const proc = spawnTestBackend(sockPath)
  t.after(() => { try { proc.kill() } catch {} cleanupStaleSocket(sockPath) })

  assert.ok(await waitForSocket(sockPath, proc), `后端未就绪 rc=${proc.exitCode} stderr=${proc._err().slice(0, 300)}`)
  assert.strictEqual(proc.exitCode, null, '后端提前退出')

  // 第一次连接
  const received1 = []
  const client1 = createGatewayClient({ sockPath, onMessage: (m) => received1.push(m) })
  client1.connect()
  assert.ok(await waitFor(() => client1.connected), 'client1 未连上')
  assert.ok(
    await waitFor(() => received1.some(isReady)),
    `未收到 ready: ${JSON.stringify(received1).slice(0, 200)}`
  )
  client1.send({ jsonrpc: '2.0', method: 'ping', id: 1 })
  assert.ok(await waitFor(() => received1.some((m) => m.id === 1)), '未收到 ping 响应')

  // 前端断开（模拟窗口崩溃/关窗）
  client1.close()
  await new Promise((r) => setTimeout(r, 500))
  assert.strictEqual(proc.exitCode, null, '前端断开后后端竟然退出了')

  // 重连（模拟重开窗口）
  const received2 = []
  const client2 = createGatewayClient({ sockPath, onMessage: (m) => received2.push(m) })
  client2.connect()
  assert.ok(await waitFor(() => client2.connected), 'client2 未连上')
  assert.ok(
    await waitFor(() => received2.some(isReady)),
    `重连未收到 ready: ${JSON.stringify(received2).slice(0, 200)}`
  )
  client2.send({ jsonrpc: '2.0', method: 'ping', id: 2 })
  assert.ok(await waitFor(() => received2.some((m) => m.id === 2)), '重连后未收到 ping 响应')
  client2.close()
})

test('EADDRINUSE 防御：第二个后端抢同一 sock 被拒，第一个存活', async (t) => {
  const sockPath = tmpSock('eaddrinuse')
  const proc1 = spawnTestBackend(sockPath)
  t.after(() => { try { proc1.kill() } catch {} cleanupStaleSocket(sockPath) })
  assert.ok(await waitForSocket(sockPath, proc1), '后端1未就绪')

  // 第二个后端绑定同一 sock → entry.py 探测到活跃进程 → 拒绝并退出
  const proc2 = spawnTestBackend(sockPath)
  t.after(() => { try { proc2.kill() } catch {} })
  const exited = await waitFor(() => proc2.exitCode !== null, 8000)
  assert.ok(exited, `第二个后端未退出（应拒绝双实例）stderr=${proc2._err().slice(0, 300)}`)
  assert.strictEqual(proc1.exitCode, null, '第一个后端被波及退出')
})

// ── TICKET-GW-MULTI：socket 后端多客户端并发 ──────────────────────────
test('GW-MULTI 多客户端并发：各自 ready + session.create 会话不串 + 一方断开另一方不受影响', async (t) => {
  const sockPath = tmpSock('multi')
  const proc = spawnTestBackend(sockPath)
  t.after(() => { try { proc.kill() } catch {} cleanupStaleSocket(sockPath) })
  assert.ok(await waitForSocket(sockPath, proc), `后端未就绪 rc=${proc.exitCode} stderr=${proc._err().slice(0, 300)}`)
  assert.strictEqual(proc.exitCode, null, '后端提前退出')

  const recvA = []
  const recvB = []
  const clientA = createGatewayClient({ sockPath, onMessage: (m) => recvA.push(m) })
  const clientB = createGatewayClient({ sockPath, onMessage: (m) => recvB.push(m) })
  clientA.connect()
  clientB.connect()

  assert.ok(await waitFor(() => clientA.connected), 'clientA 未连上')
  assert.ok(await waitFor(() => clientB.connected), 'clientB 未连上')
  assert.ok(await waitFor(() => recvA.some(isReady)), `A 未收 ready: ${JSON.stringify(recvA).slice(0, 200)}`)
  assert.ok(await waitFor(() => recvB.some(isReady)), `B 未收 ready: ${JSON.stringify(recvB).slice(0, 200)}`)

  // 各自 session.create（同一 id=1，响应必须定向回各自请求方——不串线）
  clientA.send({ jsonrpc: '2.0', method: 'session.create', id: 1 })
  clientB.send({ jsonrpc: '2.0', method: 'session.create', id: 1 })
  assert.ok(await waitFor(() => recvA.some((m) => m.id === 1)), `A 未收 session.create 响应: ${JSON.stringify(recvA).slice(0, 300)}`)
  assert.ok(await waitFor(() => recvB.some((m) => m.id === 1)), `B 未收 session.create 响应: ${JSON.stringify(recvB).slice(0, 300)}`)

  const resA = recvA.filter((m) => m.id === 1)
  const resB = recvB.filter((m) => m.id === 1)
  assert.strictEqual(resA.length, 1, `A 收到多条 id=1 响应（响应串线）: ${JSON.stringify(resA)}`)
  assert.strictEqual(resB.length, 1, `B 收到多条 id=1 响应（响应串线）: ${JSON.stringify(resB)}`)
  const sidA = resA[0].result && resA[0].result.session_id
  const sidB = resB[0].result && resB[0].result.session_id
  assert.ok(sidA, `A 响应无 session_id: ${JSON.stringify(resA[0])}`)
  assert.ok(sidB, `B 响应无 session_id: ${JSON.stringify(resB[0])}`)
  assert.notStrictEqual(sidA, sidB, '双客户端 session_id 相同（会话串了）')

  // 甲断开 → 乙不受影响（仍能 ping 往返；后端存活）
  clientA.close()
  await new Promise((r) => setTimeout(r, 300))
  clientB.send({ jsonrpc: '2.0', method: 'ping', id: 2 })
  assert.ok(await waitFor(() => recvB.some((m) => m.id === 2)), 'B 在 A 断开后未收到 ping 响应')
  assert.strictEqual(proc.exitCode, null, '后端在 A 断开后退出')

  // 全部断开 → 后端存活（BOBO_GW_IDLE_TIMEOUT=0 语义，桌面端长连断线不杀后端）
  clientB.close()
  await new Promise((r) => setTimeout(r, 300))
  assert.strictEqual(proc.exitCode, null, '全部断开后后端退出（IDLE_TIMEOUT=0 应存活）')
})
