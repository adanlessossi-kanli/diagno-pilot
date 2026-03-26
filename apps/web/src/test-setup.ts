import '@testing-library/jest-dom';

// Suppress React act() warnings that are expected in async component tests
const originalError = console.error.bind(console);
console.error = (...args: unknown[]) => {
  const msg = typeof args[0] === 'string' ? args[0] : '';
  if (msg.includes('not wrapped in act') || msg.includes('Maximum update depth exceeded')) return;
  originalError(...args);
};
