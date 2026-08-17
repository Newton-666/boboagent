// socketClient.test.js — real unix-socket round trip + reconnect (TICKET-VSC-1)
'use strict';
const test = require('node:test');
const assert = require('node:assert');
const net = require('net');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { SocketClient } = require('../out/socketClient.js');

function tmpSock() {
  return path.join(os.tmpdir(), `bobo-test-${process.pid}-${Date.now()}-${Math.random().toString(36).slice(2)}.sock`);
}

function startServer(sockPath, onConn) {
  return new Promise((resolve) => {
    const srv = net.createServer((conn) => {
      if (onConn) onConn(conn);
    });
    srv.listen(sockPath, () => resolve(srv));
  });
}

test('connect, send, receive response, receive event', async () => {
  const sock = tmpSock();
  let srv = await startServer(sock, (conn) => {
    conn.setEncoding('utf8');
    conn.on('data', (chunk) => {
      const lines = chunk.split('\n').filter(Boolean);
      for (const line of lines) {
        const req = JSON.parse(line);
        if (req.method === 'session.create') {
          conn.write(JSON.stringify({ jsonrpc: '2.0', id: req.id, result: { session_id: 's-test' } }) + '\n');
          conn.write(JSON.stringify({ jsonrpc: '2.0', method: 'event', params: { type: 'message.start', session_id: 's-test' } }) + '\n');
        }
      }
    });
  });

  const events = [];
  let resolveConnected;
  const connected = new Promise((r) => { resolveConnected = r; });
  const client = new SocketClient({
    backoffMs: 20,
    maxBackoffMs: 50,
    jitter: 0,
    onEvent: (ev) => events.push(ev),
    onConnect: () => resolveConnected(),
  });
  client.connect(sock);
  await connected;

  const result = await client.send('session.create', {});
  assert.strictEqual(result.session_id, 's-test');
  await new Promise((r) => setTimeout(r, 50));
  assert.strictEqual(events.length, 1);
  assert.strictEqual(events[0].params.type, 'message.start');

  client.close();
  srv.close();
  try { fs.unlinkSync(sock); } catch { /* ignore */ }
});

test('auto-reconnect after server drop (backoff capped)', async () => {
  const sock = tmpSock();
  const conns = [];
  let srv = await startServer(sock, (conn) => conns.push(conn));
  const connects = [];
  const client = new SocketClient({ backoffMs: 20, maxBackoffMs: 40, jitter: 0, onConnect: () => connects.push(Date.now()) });
  client.connect(sock);
  await new Promise((r) => setTimeout(r, 60));
  assert.strictEqual(connects.length, 1);

  // drop the server: force-close the client connection so it notices
  for (const c of conns) c.destroy();
  srv.close();
  try { fs.unlinkSync(sock); } catch { /* ignore */ }
  await new Promise((r) => setTimeout(r, 30));

  // restart the server on the same path -> client reconnects
  srv = await startServer(sock, () => {});
  await new Promise((r) => setTimeout(r, 200));
  assert.ok(connects.length >= 2, `expected reconnect, got ${connects.length}`);

  client.close();
  srv.close();
  try { fs.unlinkSync(sock); } catch { /* ignore */ }
});

test('send rejects when not connected', async () => {
  const client = new SocketClient();
  await assert.rejects(client.send('ping', {}), /Not connected/);
  client.close();
});

test('RPC error surfaces as rejected promise', async () => {
  const sock = tmpSock();
  const srv = await startServer(sock, (conn) => {
    conn.setEncoding('utf8');
    conn.on('data', (chunk) => {
      const req = JSON.parse(chunk.split('\n').filter(Boolean)[0]);
      conn.write(JSON.stringify({ jsonrpc: '2.0', id: req.id, error: { code: -32000, message: '会话不存在' } }) + '\n');
    });
  });
  const client = new SocketClient({ backoffMs: 20, jitter: 0 });
  client.connect(sock);
  await new Promise((r) => setTimeout(r, 60));
  await assert.rejects(client.send('prompt.submit', {}), /-32000: 会话不存在/);
  client.close();
  srv.close();
  try { fs.unlinkSync(sock); } catch { /* ignore */ }
});

test('close() stops reconnect attempts', async () => {
  const sock = tmpSock(); // nothing listening -> connection refused loop
  let disconnects = 0;
  const client = new SocketClient({
    backoffMs: 20,
    maxBackoffMs: 40,
    jitter: 0,
    onDisconnect: () => disconnects++,
  });
  client.connect(sock);
  await new Promise((r) => setTimeout(r, 80));
  client.close();
  const n = disconnects;
  await new Promise((r) => setTimeout(r, 100));
  assert.strictEqual(disconnects, n, 'no further disconnect callbacks after close');
});
