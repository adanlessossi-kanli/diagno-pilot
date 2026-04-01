import { setupServer } from 'msw/node';

/**
 * MSW server instance for API route tests.
 *
 * Usage in test files:
 *
 *   import { server } from '@/test/msw-server';
 *   import { http, HttpResponse } from 'msw';
 *
 *   beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
 *   afterEach(() => server.resetHandlers());
 *   afterAll(() => server.close());
 *
 *   // Override handlers per-test:
 *   server.use(
 *     http.get('http://backend/api/v1/patients', () =>
 *       HttpResponse.json({ items: [], total: 0 }),
 *     ),
 *   );
 */
export const server = setupServer();
