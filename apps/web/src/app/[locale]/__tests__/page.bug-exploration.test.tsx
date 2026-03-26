/**
 * Bug Condition Exploration Test — Task 1
 *
 * Property 1: Bug Condition - heroHome Key Undefined Bug
 *
 * CRITICAL: This test is EXPECTED TO FAIL on unfixed code.
 * Failure confirms the bug exists. DO NOT fix the code or the test.
 *
 * Validates: Requirements 1.1, 1.2
 */

import { describe, it, expect, vi } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import { IMAGES } from '@/lib/images';
import HomePage from '../page';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('next/image', () => ({
  default: (props: Record<string, unknown>) => (
    <img data-testid="hero-image" {...props} />
  ),
}));

// ─── Bug Condition Exploration Tests ─────────────────────────────────────────

describe('Bug Condition Exploration — IMAGES.heroHome key mismatch', () => {
  /**
   * Test Case 2: Key Existence Test
   * Confirms the key mismatch: heroHome is undefined, hero is defined.
   * This test PASSES even on unfixed code — it documents the bug condition.
   *
   * Validates: Requirement 1.2
   */
  it('IMAGES["heroHome"] is undefined (bug condition confirmed)', () => {
    // The bug: heroHome does not exist in the registry
    expect(IMAGES['heroHome']).toBeUndefined();
    // The correct key exists
    expect(IMAGES['hero']).toBeDefined();
    expect(IMAGES['hero'].src).toBeTruthy();
    expect(IMAGES['hero'].alt).toBeTruthy();
  });

  /**
   * Test Case 1: Hero Image Render Test
   * Renders HomePage and asserts Image receives a non-undefined src.
   * EXPECTED TO FAIL on unfixed code with TypeError: Cannot read properties of undefined (reading 'src')
   *
   * Validates: Requirements 1.1, 1.2
   */
  it('HomePage renders without TypeError — hero image src is defined (fails on unfixed code)', () => {
    // On unfixed code this throws: TypeError: Cannot read properties of undefined (reading 'src')
    // because IMAGES.heroHome is undefined
    expect(() => render(<HomePage />)).not.toThrow();

    const img = document.querySelector('[data-testid="hero-image"]') as HTMLImageElement;
    expect(img).not.toBeNull();
    // Assert Image receives a non-undefined src — will fail on unfixed code
    expect(img?.getAttribute('src')).toBeTruthy();
  });

  /**
   * Test Case 3: Alt Text Test
   * Renders HomePage and asserts Image receives a non-undefined alt.
   * EXPECTED TO FAIL on unfixed code (TypeError thrown before alt is even reached).
   *
   * Validates: Requirements 1.1, 1.2
   */
  it('HomePage renders without TypeError — hero image alt is defined (fails on unfixed code)', () => {
    expect(() => render(<HomePage />)).not.toThrow();

    const img = document.querySelector('[data-testid="hero-image"]') as HTMLImageElement;
    expect(img).not.toBeNull();
    // Assert Image receives a non-undefined alt — will fail on unfixed code
    expect(img?.getAttribute('alt')).toBeTruthy();
  });
});
