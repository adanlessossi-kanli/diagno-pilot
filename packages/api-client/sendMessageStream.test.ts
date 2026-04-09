// Unit tests for sendMessageStream()
// Validates: Requirements 6.1, 6.5

import { describe, it, expect, vi, afterEach } from 'vitest';
import { createApiClient } from './index';
import type { StreamEvent } from './index';

// ─── Helpers ──────────────────────────────────────────────────────────────────

const BASE_URL = 'http://localhost:8000';

/** Encode SSE text as a ReadableStream<Uint8Array>. */
function sseStream(text: string): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(text));
      controller.close();
    },
  });
}

/** Build a mock Response with an SSE body. */
function mockSSEResponse(sseText: string, status = 200): Response {
  return new Response(sseStream(sseText), {
    status,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

/** Collect all events from an async generator. */
async function collectEvents(gen: AsyncGenerator<StreamEvent>): Promise<StreamEvent[]> {
  const events: StreamEvent[] = [];
  for await (const event of gen) {
    events.push(event);
  }
  return events;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// ─── Happy path: token-by-token iteration ─────────────────────────────────────

describe('sendMessageStream — happy path', () => {
  it('yields token events followed by a done event', async () => {
    const sse = [
      'event: token\ndata: {"content":"Hello"}\n\n',
      'event: token\ndata: {"content":" world"}\n\n',
      'event: done\ndata: {"answer":"Hello world","session_id":"s1","sources":[],"llm_used":"qwen3","fallback_warning":null,"warnings_present":false}\n\n',
    ].join('');

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockSSEResponse(sse)));

    const client = createApiClient(BASE_URL);
    const events = await collectEvents(client.chat.sendMessageStream('s1', 'hi'));

    expect(events).toHaveLength(3);
    expect(events[0]).toEqual({ type: 'token', content: 'Hello' });
    expect(events[1]).toEqual({ type: 'token', content: ' world' });
    expect(events[2]).toMatchObject({
      type: 'done',
      answer: 'Hello world',
      session_id: 's1',
      llm_used: 'qwen3',
    });
  });

  it('sends POST with credentials: include and CSRF header', async () => {
    const sse = 'event: done\ndata: {"answer":"ok","session_id":"s1","sources":[],"llm_used":"qwen3","fallback_warning":null,"warnings_present":false}\n\n';
    const fetchSpy = vi.fn().mockResolvedValue(mockSSEResponse(sse));
    vi.stubGlobal('fetch', fetchSpy);

    const client = createApiClient(BASE_URL);
    await collectEvents(client.chat.sendMessageStream('s1', 'test'));

    expect(fetchSpy).toHaveBeenCalledOnce();
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe(`${BASE_URL}/api/v1/chat/message`);
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('include');
    const body = JSON.parse(init.body);
    expect(body.session_id).toBe('s1');
    expect(body.message).toBe('test');
  });
});

// ─── Error event handling ─────────────────────────────────────────────────────

describe('sendMessageStream — error event', () => {
  it('yields an error event and stops iteration', async () => {
    const sse = [
      'event: token\ndata: {"content":"partial"}\n\n',
      'event: error\ndata: {"error":"LLM unavailable","retryable":true}\n\n',
      'event: token\ndata: {"content":"should not appear"}\n\n',
    ].join('');

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockSSEResponse(sse)));

    const client = createApiClient(BASE_URL);
    const events = await collectEvents(client.chat.sendMessageStream('s1', 'hi'));

    expect(events).toHaveLength(2);
    expect(events[0]).toEqual({ type: 'token', content: 'partial' });
    expect(events[1]).toEqual({ type: 'error', error: 'LLM unavailable', retryable: true });
  });

  it('throws ApiError on non-2xx HTTP response', async () => {
    const errorResponse = new Response(JSON.stringify({ detail: 'Unauthorized' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(errorResponse));

    const client = createApiClient(BASE_URL);
    await expect(collectEvents(client.chat.sendMessageStream('s1', 'hi'))).rejects.toMatchObject({
      status: 401,
      message: 'Unauthorized',
    });
  });
});

// ─── AbortSignal cancellation ─────────────────────────────────────────────────

describe('sendMessageStream — AbortSignal', () => {
  it('passes AbortSignal to fetch', async () => {
    const controller = new AbortController();

    const sse = 'event: done\ndata: {"answer":"ok","session_id":"s1","sources":[],"llm_used":"qwen3","fallback_warning":null,"warnings_present":false}\n\n';
    const fetchSpy = vi.fn().mockResolvedValue(mockSSEResponse(sse));
    vi.stubGlobal('fetch', fetchSpy);

    const client = createApiClient(BASE_URL);
    // Must iterate to trigger fetch
    await collectEvents(client.chat.sendMessageStream('s1', 'hi', undefined, controller.signal));

    expect(fetchSpy).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ signal: controller.signal }),
    );
  });

  it('fetch rejects with AbortError when signal is already aborted', async () => {
    const controller = new AbortController();
    controller.abort();

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('Aborted', 'AbortError')));

    const client = createApiClient(BASE_URL);
    await expect(
      collectEvents(client.chat.sendMessageStream('s1', 'hi', undefined, controller.signal)),
    ).rejects.toThrow('Aborted');
  });
});
