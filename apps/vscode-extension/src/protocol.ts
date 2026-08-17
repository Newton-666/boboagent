/**
 * protocol.ts — bobo gateway JSON-RPC 2.0 line protocol (TICKET-018 socket mode).
 *
 * Wire format (verified against bobo_tui_gateway/transport.py + entry.py):
 *   request:  {"jsonrpc":"2.0","method":"...","params":{...},"id":N}\n
 *   response: {"jsonrpc":"2.0","result":{...},"id":N}\n   or  {"jsonrpc":"2.0","error":{...},"id":N}\n
 *   event:    {"jsonrpc":"2.0","method":"event","params":{"type":"...",...}}\n  (no id)
 *
 * Each JSON object is exactly one line, UTF-8, terminated by \n.
 */

/** One outbound RPC request. */
export interface RpcRequest {
  jsonrpc: '2.0';
  method: string;
  params?: Record<string, unknown>;
  id: number;
}

/** A server-pushed event (method === 'event', no id). */
export interface RpcEvent {
  jsonrpc: '2.0';
  method: 'event';
  params: {
    type: string;
    session_id?: string;
    [k: string]: unknown;
  };
}

/** A response to a request with matching id. */
export interface RpcResponse {
  jsonrpc: '2.0';
  id: number;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

/** Parse one line. Returns request/response/event, or null on parse error. */
export function parseLine(line: string): RpcRequest | RpcResponse | RpcEvent | null {
  if (!line || !line.trim()) return null;
  try {
    return JSON.parse(line) as RpcRequest | RpcResponse | RpcEvent;
  } catch {
    return null;
  }
}

/** Encode a request as one protocol line (JSON + \n, no trailing spaces). */
export function encodeRequest(method: string, params: Record<string, unknown> | undefined, id: number): string {
  const req: RpcRequest = { jsonrpc: '2.0', method, params, id };
  return JSON.stringify(req) + '\n';
}

/** Encode a bare response object (used by tests / mocks). */
export function encodeResponse(id: number, result?: unknown, error?: { code: number; message: string }): string {
  const resp: RpcResponse = { jsonrpc: '2.0', id, result, error };
  return JSON.stringify(resp) + '\n';
}

/** Encode an event object (used by tests / mocks). */
export function encodeEvent(type: string, extra: Record<string, unknown> = {}): string {
  const ev: RpcEvent = { jsonrpc: '2.0', method: 'event', params: { type, ...extra } };
  return JSON.stringify(ev) + '\n';
}

/** True when a parsed object is a server event. */
export function isEvent(m: RpcRequest | RpcResponse | RpcEvent | null): m is RpcEvent {
  return !!m && (m as RpcEvent).method === 'event';
}

/** True when a parsed object is a response (has id + (result|error)). */
export function isResponse(m: RpcRequest | RpcResponse | RpcEvent | null): m is RpcResponse {
  return !!m && (m as RpcResponse).id !== undefined && ((m as RpcResponse).result !== undefined || (m as RpcResponse).error !== undefined);
}
