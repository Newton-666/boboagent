/**
 * socketClient.ts — JSON-RPC client over a unix socket with auto-reconnect
 * and exponential backoff. Pure Node — no vscode import, unit-testable.
 *
 * Protocol: each line is one JSON object (see protocol.ts). Requests carry an
 * incrementing id; responses are matched by id; events (method==='event') are
 * dispatched to onEvent callbacks.
 */

import * as net from 'net';
import {
  encodeRequest,
  parseLine,
  isEvent,
  isResponse,
  RpcResponse,
  RpcEvent,
} from './protocol';

const DEFAULT_BACKOFF_MS = 500;
const MAX_BACKOFF_MS = 10_000;

export interface SocketClientOptions {
  /** Called after a successful connect (once per (re)connect). */
  onConnect?: (sockPath: string) => void;
  /** Called when the socket disconnects (including initial failures). */
  onDisconnect?: (err?: Error) => void;
  /** Called on every server event. */
  onEvent?: (ev: RpcEvent) => void;
  /** Backoff base in ms (default 500). */
  backoffMs?: number;
  /** Max backoff in ms (default 10000). */
  maxBackoffMs?: number;
  /** Jitter fraction 0..1 (default 0.2). */
  jitter?: number;
  /** Injectable clock (tests). */
  now?: () => number;
}

interface Pending {
  resolve: (v: unknown) => void;
  reject: (e: Error) => void;
  timer: NodeJS.Timeout;
}

export class SocketClient {
  private sockPath: string | null = null;
  private sock: net.Socket | null = null;
  private buf = '';
  private nextId = 1;
  private pending = new Map<number, Pending>();
  private closed = false;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private attempt = 0;
  private connectInFlight = false;
  private readonly opts: Required<Pick<SocketClientOptions, 'backoffMs' | 'maxBackoffMs' | 'jitter'>>;
  private readonly now: () => number;

  /** Public callbacks — settable at construction (opts) or at runtime. */
  onConnect: (sockPath: string) => void = () => {};
  onDisconnect: (err?: Error) => void = () => {};
  onEvent: (ev: RpcEvent) => void = () => {};

  constructor(opts: SocketClientOptions = {}) {
    this.opts = {
      backoffMs: opts.backoffMs ?? DEFAULT_BACKOFF_MS,
      maxBackoffMs: opts.maxBackoffMs ?? MAX_BACKOFF_MS,
      jitter: opts.jitter ?? 0.2,
    };
    this.now = opts.now || (() => Date.now());
    if (opts.onConnect) this.onConnect = opts.onConnect;
    if (opts.onDisconnect) this.onDisconnect = opts.onDisconnect;
    if (opts.onEvent) this.onEvent = opts.onEvent;
  }

  /** Start connecting (idempotent). */
  connect(sockPath: string): void {
    if (this.closed) return;
    this.sockPath = sockPath;
    this.scheduleReconnect(0);
  }

  /** Send a request, resolve with the result object. */
  send<T = unknown>(method: string, params?: Record<string, unknown>, timeoutMs = 60_000): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      if (!this.sock || !this.sockPath) {
        reject(new Error('Not connected to bobo gateway'));
        return;
      }
      const id = this.nextId++;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`RPC ${method} timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      this.pending.set(id, { resolve: resolve as (v: unknown) => void, reject, timer });
      this.sock.write(encodeRequest(method, params, id));
    });
  }

  /** Close the client; no reconnect afterwards. */
  close(): void {
    this.closed = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    this.rejectAll(new Error('client closed'));
    if (this.sock) {
      try {
        this.sock.destroy();
      } catch {
        /* ignore */
      }
      this.sock = null;
    }
  }

  get connected(): boolean {
    return !!this.sock && !this.sock.destroyed;
  }

  // ── internals ──

  private scheduleReconnect(delayMs: number): void {
    if (this.closed || this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.tryConnect();
    }, delayMs);
  }

  private nextDelay(): number {
    const base = Math.min(this.opts.backoffMs * Math.pow(2, this.attempt), this.opts.maxBackoffMs);
    const j = this.opts.jitter > 0 ? 1 + (Math.random() - 0.5) * 2 * this.opts.jitter : 1;
    return Math.round(base * j);
  }

  private tryConnect(): void {
    if (this.closed || this.connectInFlight || !this.sockPath) return;
    this.connectInFlight = true;
    const sock = net.createConnection({ path: this.sockPath });
    sock.setNoDelay(true);

    sock.on('connect', () => {
      this.connectInFlight = false;
      this.attempt = 0;
      this.sock = sock;
      this.buf = '';
      this.onConnect(this.sockPath as string);
    });

    sock.on('data', (chunk: Buffer) => {
      this.buf += chunk.toString('utf8');
      this.drainBuffer();
    });

    sock.on('error', (err: Error) => {
      this.connectInFlight = false;
      if (this.sock === sock) this.sock = null;
      this.onDisconnect(err);
      this.scheduleReconnect(this.nextDelay());
      this.attempt++;
    });

    sock.on('close', () => {
      this.connectInFlight = false;
      if (this.sock === sock) this.sock = null;
      this.onDisconnect();
      this.rejectAll(new Error('gateway disconnected'));
      this.scheduleReconnect(this.nextDelay());
      this.attempt++;
    });
  }

  private drainBuffer(): void {
    let idx: number;
    while ((idx = this.buf.indexOf('\n')) >= 0) {
      const line = this.buf.slice(0, idx);
      this.buf = this.buf.slice(idx + 1);
      const msg = parseLine(line);
      if (!msg) continue;
      if (isEvent(msg)) {
        this.onEvent(msg);
      } else if (isResponse(msg)) {
        this.handleResponse(msg);
      }
      // requests from server are not expected; ignore
    }
  }

  private handleResponse(resp: RpcResponse): void {
    const p = this.pending.get(resp.id);
    if (!p) return;
    this.pending.delete(resp.id);
    clearTimeout(p.timer);
    if (resp.error) {
      p.reject(new Error(`${resp.error.code}: ${resp.error.message}`));
    } else {
      p.resolve(resp.result);
    }
  }

  private rejectAll(err: Error): void {
    for (const [, p] of this.pending) {
      clearTimeout(p.timer);
      p.reject(err);
    }
    this.pending.clear();
  }
}
