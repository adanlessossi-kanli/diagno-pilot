/**
 * Property-based tests for DocumentChat logic.
 *
 * Property 8: Citation Chips Rendered for Non-Empty Sources
 * Property 13: Highlight BBox Positioning
 * Property 14: Document Chat SSE Stream Completeness
 * Property 15: Document Chat Stream Abort Safety
 *
 * Uses fast-check with { numRuns: 100 }.
 */

import { describe, it, expect } from 'vitest';
import fc from 'fast-check';

// ─── Types ────────────────────────────────────────────────────────────────────

interface HighlightInfo {
  bbox: [number, number, number, number];
  page: number;
}

interface DocumentSource {
  documentId: string;
  title: string;
  source: string;
  section?: string;
  excerpt?: string;
  page?: number;
  highlight?: HighlightInfo;
  confidenceScore?: number;
}

interface StreamEvent {
  type: 'token' | 'done';
  content?: string;
  answer?: string;
  session_id?: string;
  sources?: DocumentSource[];
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: DocumentSource[];
  timestamp: string;
  interrupted?: boolean;
}

// ─── Pure functions under test ────────────────────────────────────────────────

/**
 * Property 8: Count how many CitationChip components would be rendered
 * for a given sources array.
 */
function countCitationChips(sources: DocumentSource[]): number {
  return sources.length > 0 ? sources.length : 0;
}

/**
 * Property 13: Compute highlight overlay position in rendered pixel coordinates
 * from PDF user-space bbox coordinates.
 */
export function computeHighlightPosition(
  bbox: [number, number, number, number],
  pdfPageWidth: number,
  pdfPageHeight: number,
  renderedWidth: number,
  renderedHeight: number,
): { left: number; top: number; width: number; height: number } {
  const scaleX = renderedWidth / pdfPageWidth;
  const scaleY = renderedHeight / pdfPageHeight;
  const [x0, y0, x1, y1] = bbox;
  return {
    left: x0 * scaleX,
    top: y0 * scaleY,
    width: (x1 - x0) * scaleX,
    height: (y1 - y0) * scaleY,
  };
}

/**
 * Property 14: Process a sequence of SSE stream events and extract
 * concatenated tokens, final answer, session_id, and sources.
 */
function processStreamEvents(events: StreamEvent[]): {
  concatenatedTokens: string;
  finalAnswer: string | null;
  sessionId: string | null;
  sources: DocumentSource[] | null;
} {
  let concatenated = '';
  let finalAnswer: string | null = null;
  let sessionId: string | null = null;
  let sources: DocumentSource[] | null = null;

  for (const event of events) {
    if (event.type === 'token') {
      concatenated += event.content;
    } else if (event.type === 'done') {
      finalAnswer = event.answer ?? null;
      sessionId = event.session_id ?? null;
      sources = event.sources ?? null;
    }
  }

  return { concatenatedTokens: concatenated, finalAnswer, sessionId, sources };
}

/**
 * Property 15: Handle abort by filtering empty placeholder messages
 * and ensuring no error is shown.
 */
function handleAbort(
  messages: ChatMessage[],
  placeholderId: string,
): { filteredMessages: ChatMessage[]; showError: boolean } {
  const filtered = messages.filter(
    (m) => !(m.id === placeholderId && m.content === ''),
  );
  return { filteredMessages: filtered, showError: false };
}

// ─── Arbitraries ──────────────────────────────────────────────────────────────

const documentSourceArb: fc.Arbitrary<DocumentSource> = fc.record({
  documentId: fc.uuid(),
  title: fc.string({ minLength: 1, maxLength: 50 }),
  source: fc.string({ minLength: 1, maxLength: 30 }),
  section: fc.option(fc.string({ minLength: 1, maxLength: 30 }), { nil: undefined }),
  excerpt: fc.option(fc.string({ minLength: 1, maxLength: 100 }), { nil: undefined }),
  page: fc.option(fc.nat({ max: 500 }), { nil: undefined }),
  highlight: fc.option(
    fc.record({
      bbox: fc.tuple(
        fc.double({ min: 0, max: 500, noNaN: true }),
        fc.double({ min: 0, max: 500, noNaN: true }),
        fc.double({ min: 0, max: 500, noNaN: true }),
        fc.double({ min: 0, max: 500, noNaN: true }),
      ) as fc.Arbitrary<[number, number, number, number]>,
      page: fc.nat({ max: 500 }),
    }),
    { nil: undefined },
  ),
  confidenceScore: fc.option(fc.double({ min: 0, max: 1, noNaN: true }), { nil: undefined }),
});

const chatMessageArb: fc.Arbitrary<ChatMessage> = fc.record({
  id: fc.uuid(),
  role: fc.constantFrom('user' as const, 'assistant' as const),
  content: fc.string({ maxLength: 200 }),
  sources: fc.option(fc.array(documentSourceArb, { minLength: 0, maxLength: 5 }), { nil: undefined }),
  timestamp: fc.integer({
    min: new Date('2020-01-01').getTime(),
    max: new Date('2030-12-31').getTime(),
  }).map((ts) => new Date(ts).toISOString()),
  interrupted: fc.option(fc.boolean(), { nil: undefined }),
});

// ─── Property 8: Citation Chips Rendered for Non-Empty Sources ────────────────
// **Validates: Requirements 6.1**

describe('Property 8: Citation Chips Rendered for Non-Empty Sources', () => {
  it('chip count equals sources.length for any sources array of length 0–10', () => {
    fc.assert(
      fc.property(
        fc.array(documentSourceArb, { minLength: 0, maxLength: 10 }),
        (sources) => {
          const chipCount = countCitationChips(sources);
          if (sources.length > 0) {
            expect(chipCount).toBe(sources.length);
          } else {
            expect(chipCount).toBe(0);
          }
        },
      ),
      { numRuns: 100 },
    );
  });

  it('returns 0 for an empty sources array', () => {
    fc.assert(
      fc.property(fc.constant([] as DocumentSource[]), (sources: DocumentSource[]) => {
        expect(countCitationChips(sources)).toBe(0);
      }),
      { numRuns: 100 },
    );
  });

  it('returns exactly K for any non-empty sources array of length K', () => {
    fc.assert(
      fc.property(
        fc.array(documentSourceArb, { minLength: 1, maxLength: 10 }),
        (sources) => {
          expect(countCitationChips(sources)).toBe(sources.length);
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ─── Property 13: Highlight BBox Positioning ──────────────────────────────────
// **Validates: Requirements 6.4**

describe('Property 13: Highlight BBox Positioning', () => {
  // Arbitrary for valid bbox where x1 >= x0 and y1 >= y0
  const validBboxArb = fc
    .tuple(
      fc.double({ min: 0, max: 500, noNaN: true }),
      fc.double({ min: 0, max: 500, noNaN: true }),
      fc.double({ min: 0, max: 500, noNaN: true }),
      fc.double({ min: 0, max: 500, noNaN: true }),
    )
    .map(([a, b, c, d]) => {
      const x0 = Math.min(a, c);
      const x1 = Math.max(a, c);
      const y0 = Math.min(b, d);
      const y1 = Math.max(b, d);
      return [x0, y0, x1, y1] as [number, number, number, number];
    });

  const positiveDimArb = fc.double({ min: 1, max: 2000, noNaN: true });

  it('computed position is within the rendered area when bbox is within PDF page', () => {
    // Generate page dimensions first, then constrain bbox within them
    const bboxWithinPageArb = positiveDimArb.chain((pdfW) =>
      positiveDimArb.chain((pdfH) =>
        fc
          .tuple(
            fc.double({ min: 0, max: pdfW, noNaN: true }),
            fc.double({ min: 0, max: pdfH, noNaN: true }),
            fc.double({ min: 0, max: pdfW, noNaN: true }),
            fc.double({ min: 0, max: pdfH, noNaN: true }),
          )
          .map(([a, b, c, d]) => ({
            bbox: [Math.min(a, c), Math.min(b, d), Math.max(a, c), Math.max(b, d)] as [number, number, number, number],
            pdfW,
            pdfH,
          })),
      ),
    );

    fc.assert(
      fc.property(
        bboxWithinPageArb,
        positiveDimArb,
        positiveDimArb,
        ({ bbox, pdfW, pdfH }, rendW, rendH) => {
          const pos = computeHighlightPosition(bbox, pdfW, pdfH, rendW, rendH);
          // Position + size should not exceed rendered dimensions
          expect(pos.left + pos.width).toBeLessThanOrEqual(rendW + 1e-6);
          expect(pos.top + pos.height).toBeLessThanOrEqual(rendH + 1e-6);
          // All values should be non-negative
          expect(pos.left).toBeGreaterThanOrEqual(-1e-6);
          expect(pos.top).toBeGreaterThanOrEqual(-1e-6);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('width and height are non-negative when x1 >= x0 and y1 >= y0', () => {
    fc.assert(
      fc.property(
        validBboxArb,
        positiveDimArb,
        positiveDimArb,
        positiveDimArb,
        positiveDimArb,
        (bbox, pdfW, pdfH, rendW, rendH) => {
          const pos = computeHighlightPosition(bbox, pdfW, pdfH, rendW, rendH);
          expect(pos.width).toBeGreaterThanOrEqual(-1e-6);
          expect(pos.height).toBeGreaterThanOrEqual(-1e-6);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('doubling rendered dimensions doubles pixel positions', () => {
    fc.assert(
      fc.property(
        validBboxArb,
        positiveDimArb,
        positiveDimArb,
        positiveDimArb,
        positiveDimArb,
        (bbox, pdfW, pdfH, rendW, rendH) => {
          const pos1 = computeHighlightPosition(bbox, pdfW, pdfH, rendW, rendH);
          const pos2 = computeHighlightPosition(bbox, pdfW, pdfH, rendW * 2, rendH * 2);

          expect(pos2.left).toBeCloseTo(pos1.left * 2, 6);
          expect(pos2.top).toBeCloseTo(pos1.top * 2, 6);
          expect(pos2.width).toBeCloseTo(pos1.width * 2, 6);
          expect(pos2.height).toBeCloseTo(pos1.height * 2, 6);
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ─── Property 14: Document Chat SSE Stream Completeness ──────────────────────
// **Validates: Requirements 5.2, 5.5, 7.1**

describe('Property 14: Document Chat SSE Stream Completeness', () => {
  it('concatenation of token contents equals done.answer when done.answer matches', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ maxLength: 50 }), { minLength: 1, maxLength: 20 }),
        fc.uuid(),
        fc.array(documentSourceArb, { minLength: 0, maxLength: 5 }),
        (tokenContents, sessionId, sources) => {
          const concatenated = tokenContents.join('');

          // Build events: token events followed by a done event
          const events: StreamEvent[] = [
            ...tokenContents.map((content) => ({
              type: 'token' as const,
              content,
            })),
            {
              type: 'done' as const,
              answer: concatenated,
              session_id: sessionId,
              sources,
            },
          ];

          const result = processStreamEvents(events);
          expect(result.concatenatedTokens).toBe(result.finalAnswer);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('done event always includes session_id (non-empty) and sources array', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ maxLength: 50 }), { minLength: 0, maxLength: 10 }),
        fc.string({ minLength: 1, maxLength: 50 }),
        fc.array(documentSourceArb, { minLength: 0, maxLength: 5 }),
        (tokenContents, sessionId, sources) => {
          const events: StreamEvent[] = [
            ...tokenContents.map((content) => ({
              type: 'token' as const,
              content,
            })),
            {
              type: 'done' as const,
              answer: tokenContents.join(''),
              session_id: sessionId,
              sources,
            },
          ];

          const result = processStreamEvents(events);
          expect(result.sessionId).toBeTruthy();
          expect(typeof result.sessionId).toBe('string');
          expect(result.sessionId!.length).toBeGreaterThan(0);
          expect(result.sources).not.toBeNull();
          expect(Array.isArray(result.sources)).toBe(true);
        },
      ),
      { numRuns: 100 },
    );
  });
});

// ─── Property 15: Document Chat Stream Abort Safety ──────────────────────────
// **Validates: Requirements 5.6**

describe('Property 15: Document Chat Stream Abort Safety', () => {
  it('after abort, showError is always false', () => {
    fc.assert(
      fc.property(
        fc.array(chatMessageArb, { minLength: 0, maxLength: 10 }),
        fc.uuid(),
        (messages, placeholderId) => {
          const result = handleAbort(messages, placeholderId);
          expect(result.showError).toBe(false);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('empty placeholder messages (matching id with empty content) are removed', () => {
    fc.assert(
      fc.property(
        fc.array(chatMessageArb, { minLength: 0, maxLength: 10 }),
        fc.uuid(),
        (otherMessages, placeholderId) => {
          // Insert an empty placeholder message
          const placeholder: ChatMessage = {
            id: placeholderId,
            role: 'assistant',
            content: '',
            timestamp: new Date().toISOString(),
          };
          const messages = [...otherMessages, placeholder];

          const result = handleAbort(messages, placeholderId);

          // The empty placeholder should be removed
          const hasEmptyPlaceholder = result.filteredMessages.some(
            (m) => m.id === placeholderId && m.content === '',
          );
          expect(hasEmptyPlaceholder).toBe(false);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('non-empty messages and messages with different IDs are preserved', () => {
    fc.assert(
      fc.property(
        fc.array(chatMessageArb.filter((m) => m.content.length > 0), { minLength: 1, maxLength: 10 }),
        fc.uuid(),
        (nonEmptyMessages, placeholderId) => {
          // Ensure none of the messages have the placeholder ID
          const messages = nonEmptyMessages.map((m, i) => ({
            ...m,
            id: `other-${i}`,
          }));

          const result = handleAbort(messages, placeholderId);
          expect(result.filteredMessages.length).toBe(messages.length);
          expect(result.filteredMessages).toEqual(messages);
        },
      ),
      { numRuns: 100 },
    );
  });

  it('placeholder with content (partial response) is kept', () => {
    fc.assert(
      fc.property(
        fc.array(chatMessageArb, { minLength: 0, maxLength: 5 }),
        fc.uuid(),
        fc.string({ minLength: 1, maxLength: 100 }),
        (otherMessages, placeholderId, partialContent) => {
          // Insert a placeholder with partial content
          const placeholder: ChatMessage = {
            id: placeholderId,
            role: 'assistant',
            content: partialContent,
            timestamp: new Date().toISOString(),
          };
          const messages = [...otherMessages, placeholder];

          const result = handleAbort(messages, placeholderId);

          // The placeholder with content should be preserved
          const kept = result.filteredMessages.find(
            (m) => m.id === placeholderId && m.content === partialContent,
          );
          expect(kept).toBeDefined();
        },
      ),
      { numRuns: 100 },
    );
  });
});
