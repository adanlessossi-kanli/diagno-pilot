import { renderHook, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { useRequestTimeout } from './useRequestTimeout';

describe('useRequestTimeout', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns initial state with isWarning and isAborted both false', () => {
    const { result } = renderHook(() => useRequestTimeout());
    expect(result.current.isWarning).toBe(false);
    expect(result.current.isAborted).toBe(false);
  });

  it('sets isWarning to true after 15s (default warningMs)', () => {
    const { result } = renderHook(() => useRequestTimeout());
    const controller = new AbortController();

    act(() => {
      result.current.startTimer(controller);
    });

    act(() => {
      vi.advanceTimersByTime(15000);
    });

    expect(result.current.isWarning).toBe(true);
    expect(result.current.isAborted).toBe(false);
    expect(controller.signal.aborted).toBe(false);
  });

  it('sets isAborted to true and aborts controller after 30s (default abortMs)', () => {
    const { result } = renderHook(() => useRequestTimeout());
    const controller = new AbortController();

    act(() => {
      result.current.startTimer(controller);
    });

    act(() => {
      vi.advanceTimersByTime(30000);
    });

    expect(result.current.isWarning).toBe(true);
    expect(result.current.isAborted).toBe(true);
    expect(controller.signal.aborted).toBe(true);
  });

  it('calls onWarning callback at warning threshold', () => {
    const onWarning = vi.fn();
    const { result } = renderHook(() => useRequestTimeout({ onWarning }));
    const controller = new AbortController();

    act(() => {
      result.current.startTimer(controller);
    });

    act(() => {
      vi.advanceTimersByTime(15000);
    });

    expect(onWarning).toHaveBeenCalledOnce();
  });

  it('calls onAbort callback at abort threshold', () => {
    const onAbort = vi.fn();
    const { result } = renderHook(() => useRequestTimeout({ onAbort }));
    const controller = new AbortController();

    act(() => {
      result.current.startTimer(controller);
    });

    act(() => {
      vi.advanceTimersByTime(30000);
    });

    expect(onAbort).toHaveBeenCalledOnce();
  });

  it('respects custom warningMs and abortMs', () => {
    const { result } = renderHook(() =>
      useRequestTimeout({ warningMs: 5000, abortMs: 10000 }),
    );
    const controller = new AbortController();

    act(() => {
      result.current.startTimer(controller);
    });

    act(() => {
      vi.advanceTimersByTime(5000);
    });

    expect(result.current.isWarning).toBe(true);
    expect(result.current.isAborted).toBe(false);

    act(() => {
      vi.advanceTimersByTime(5000);
    });

    expect(result.current.isAborted).toBe(true);
    expect(controller.signal.aborted).toBe(true);
  });

  it('clearTimer resets state and prevents timers from firing', () => {
    const onWarning = vi.fn();
    const onAbort = vi.fn();
    const { result } = renderHook(() =>
      useRequestTimeout({ onWarning, onAbort }),
    );
    const controller = new AbortController();

    act(() => {
      result.current.startTimer(controller);
    });

    act(() => {
      vi.advanceTimersByTime(10000);
    });

    act(() => {
      result.current.clearTimer();
    });

    expect(result.current.isWarning).toBe(false);
    expect(result.current.isAborted).toBe(false);

    act(() => {
      vi.advanceTimersByTime(25000);
    });

    expect(onWarning).not.toHaveBeenCalled();
    expect(onAbort).not.toHaveBeenCalled();
    expect(controller.signal.aborted).toBe(false);
  });

  it('startTimer clears previous timers before starting new ones', () => {
    const { result } = renderHook(() => useRequestTimeout());
    const controller1 = new AbortController();
    const controller2 = new AbortController();

    act(() => {
      result.current.startTimer(controller1);
    });

    act(() => {
      vi.advanceTimersByTime(10000);
    });

    act(() => {
      result.current.startTimer(controller2);
    });

    // Advance past the original 30s mark — controller1 should NOT be aborted
    act(() => {
      vi.advanceTimersByTime(20000);
    });

    expect(controller1.signal.aborted).toBe(false);
    // controller2 warning should have fired (20s > 15s)
    expect(result.current.isWarning).toBe(true);
    expect(result.current.isAborted).toBe(false);

    act(() => {
      vi.advanceTimersByTime(10000);
    });

    expect(result.current.isAborted).toBe(true);
    expect(controller2.signal.aborted).toBe(true);
  });

  it('cleans up timers on unmount', () => {
    const onWarning = vi.fn();
    const onAbort = vi.fn();
    const { result, unmount } = renderHook(() =>
      useRequestTimeout({ onWarning, onAbort }),
    );
    const controller = new AbortController();

    act(() => {
      result.current.startTimer(controller);
    });

    unmount();

    act(() => {
      vi.advanceTimersByTime(35000);
    });

    // Callbacks should not fire after unmount
    expect(onWarning).not.toHaveBeenCalled();
    expect(onAbort).not.toHaveBeenCalled();
    expect(controller.signal.aborted).toBe(false);
  });
});
