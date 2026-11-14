import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { useCallbackRefState } from '../useCallbackRefState';

describe('useCallbackRefState', () => {
  it('stores and updates a value through the stable callback', () => {
    const { result } = renderHook(() => useCallbackRefState<number>());

    expect(result.current[0]).toBeNull();
    const setRef = result.current[1];

    act(() => setRef(42));
    expect(result.current[0]).toBe(42);

    act(() => setRef(null));
    expect(result.current[0]).toBeNull();
  });

  it('returns the same callback between renders', () => {
    const { result, rerender } = renderHook(() => useCallbackRefState<string>());
    const first = result.current[1];

    rerender();
    expect(result.current[1]).toBe(first);
  });
});
