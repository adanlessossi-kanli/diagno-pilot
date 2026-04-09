// Feature: llm-response-streaming, Property 7: Frontend SSE Parse Round-Trip
// Validates: Requirements 6.2, 6.3

import { describe, it, expect } from 'vitest';
import * as fc from 'fast-check';
import { parseSSEStream } from './index';
import type { StreamEvent } from './index';

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Encode a string as a ReadableStream<Uint8Array> for parseSSEStream. */
function textToStream(text: string): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(text));
      controller.close();
    },
  });
}

/** Serialize a StreamEvent to SSE wire format. */
function serializeEvent(event: StreamEvent): string {
  let eventType: string;
  let data: Record<string, unknown>;

  switch (event.type) {
    case 'token':
      eventType = 'token';
      data = { content: event.content };
      break;
    case 'done':
      eventType = 'done';
      data = {
        answer: event.answer,
        session_id: event.session_id,
        sources: event.sources,
        llm_used: event.llm_used,
        fallback_warning: event.fallback_warning,
        warnings_present: event.warnings_present,
      };
      break;
    case 'error':
      eventType = 'error';
      data = { error: event.error, retryable: event.retryable };
      break;
  }

  return `event: ${eventType}\ndata: ${JSON.stringify(data)}\n\n`;
}

/** Collect all events from an async generator. */
async function collectEvents(gen: AsyncGenerator<StreamEvent>): Promise<StreamEvent[]> {
  const events: StreamEvent[] = [];
  for await (const event of gen) {
    events.push(event);
  }
  return events;
}

// ─── Arbitraries ──────────────────────────────────────────────────────────────

// Safe string that won't break JSON serialization
const safeStringArb = fc.string({ minLength: 1, maxLength: 50 }).filter((s) => {
  try { JSON.parse(JSON.stringify(s)); return true; } catch { return false; }
});

const sourceArb = fc.record({
  title: safeStringArb,
  source: safeStringArb,
  page: fc.option(fc.nat({ max: 500 }), { nil: undefined }),
});

const tokenEventArb: fc.Arbitrary<StreamEvent> = safeStringArb.map((content) => ({
  type: 'token' as const,
  content,
}));

const doneEventArb: fc.Arbitrary<StreamEvent> = fc.record({
  type: fc.constant('done' as const),
  answer: safeStringArb,
  session_id: fc.uuid(),
  sources: fc.array(sourceArb, { minLength: 0, maxLength: 3 }) as fc.Arbitrary<StreamEvent extends { type: 'done'; sources: infer S } ? S : never>,
  llm_used: safeStringArb,
  fallback_warning: fc.option(safeStringArb, { nil: null }),
  warnings_present: fc.boolean(),
});

const errorEventArb: fc.Arbitrary<StreamEvent> = fc.record({
  type: fc.constant('error' as const),
  error: safeStringArb,
  retryable: fc.boolean(),
});

// A stream is: 0+ token events, then exactly one terminal (done or error)
const streamArb = fc.record({
  tokens: fc.array(tokenEventArb, { minLength: 0, maxLength: 10 }),
  terminal: fc.oneof(doneEventArb, errorEventArb),
});

// ─── Property 7: Frontend SSE Parse Round-Trip ────────────────────────────────

describe('Property 7: Frontend SSE Parse Round-Trip', () => {
  it('parseSSEStream yields StreamEvents matching the serialized input', async () => {
    await fc.assert(
      fc.asyncProperty(streamArb, async ({ tokens, terminal }) => {
        const allEvents = [...tokens, terminal];
        const sseText = allEvents.map(serializeEvent).join('');
        const stream = textToStream(sseText);
        const parsed = await collectEvents(parseSSEStream(stream));

        // Must yield same number of events
        expect(parsed).toHaveLength(allEvents.length);

        // Each parsed event must match the original
        for (let i = 0; i < allEvents.length; i++) {
          const original = allEvents[i];
          const result = parsed[i];
          expect(result.type).toBe(original.type);

          if (original.type === 'token' && result.type === 'token') {
            expect(result.content).toBe(original.content);
          } else if (original.type === 'done' && result.type === 'done') {
            expect(result.answer).toBe(original.answer);
            expect(result.session_id).toBe(original.session_id);
            expect(result.llm_used).toBe(original.llm_used);
            expect(result.fallback_warning).toBe(original.fallback_warning);
            expect(result.warnings_present).toBe(original.warnings_present);
            expect(result.sources).toEqual(original.sources);
          } else if (original.type === 'error' && result.type === 'error') {
            expect(result.error).toBe(original.error);
            expect(result.retryable).toBe(original.retryable);
          }
        }
      }),
      { numRuns: 100 },
    );
  });

  it('parseSSEStream stops after a done event even if more data follows', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.array(tokenEventArb, { minLength: 1, maxLength: 5 }),
        doneEventArb,
        fc.array(tokenEventArb, { minLength: 1, maxLength: 3 }),
        async (tokens, done, trailing) => {
          const allSSE = [...tokens, done, ...trailing].map(serializeEvent).join('');
          const stream = textToStream(allSSE);
          const parsed = await collectEvents(parseSSEStream(stream));

          // Should have tokens + done, no trailing tokens
          expect(parsed).toHaveLength(tokens.length + 1);
          expect(parsed[parsed.length - 1].type).toBe('done');
        },
      ),
      { numRuns: 100 },
    );
  });

  it('parseSSEStream stops after an error event even if more data follows', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.array(tokenEventArb, { minLength: 0, maxLength: 5 }),
        errorEventArb,
        fc.array(tokenEventArb, { minLength: 1, maxLength: 3 }),
        async (tokens, error, trailing) => {
          const allSSE = [...tokens, error, ...trailing].map(serializeEvent).join('');
          const stream = textToStream(allSSE);
          const parsed = await collectEvents(parseSSEStream(stream));

          expect(parsed).toHaveLength(tokens.length + 1);
          expect(parsed[parsed.length - 1].type).toBe('error');
        },
      ),
      { numRuns: 100 },
    );
  });
});
