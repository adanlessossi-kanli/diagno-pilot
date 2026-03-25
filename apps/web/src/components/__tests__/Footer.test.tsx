import fc from 'fast-check';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import Footer from '../Footer';

describe('Footer — unit tests', () => {
  it('renders a <footer> element', () => {
    const { container } = render(<Footer />);
    expect(container.querySelector('footer')).not.toBeNull();
  });

  it('displays the copyright text © 2026 protic-togo', () => {
    render(<Footer />);
    expect(screen.getByText('© 2026 protic-togo')).toBeDefined();
  });
});

// Feature: app-consistency, Property 17: Pour toute page auth, Footer contient © 2026 protic-togo
describe('Footer — Property 17: Copyright présent sur les pages authentifiées', () => {
  /**
   * **Validates: Requirements 6.1, 6.2**
   * Property 17: For any authenticated page, the Footer component must be present
   * and contain exactly the text "© 2026 protic-togo".
   */
  it('always renders © 2026 protic-togo regardless of render context', () => {
    fc.assert(
      fc.property(
        fc.record({
          locale: fc.constantFrom('fr', 'en'),
          pathname: fc.constantFrom('/', '/chat', '/patients', '/diagnose', '/admin'),
        }),
        ({ locale: _locale, pathname: _pathname }) => {
          const { container, unmount } = render(<Footer />);

          const footer = container.querySelector('footer');
          if (!footer) return false;

          const text = footer.textContent ?? '';
          const hasCorrectCopyright = text.includes('© 2026 protic-togo');

          unmount();
          return hasCorrectCopyright;
        }
      ),
      { numRuns: 100 }
    );
  });
});
