import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { debounce } from '../debounce';

describe('debounce', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('runs once after the delay with the latest arguments', () => {
    const fn = vi.fn();
    const debounced = debounce(fn, 200);

    debounced('a');
    debounced('b');

    expect(fn).not.toHaveBeenCalled();
    vi.advanceTimersByTime(200);
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith('b');
  });

  it('flush executes immediately and cancels the timer', () => {
    const fn = vi.fn();
    const debounced = debounce(fn, 200);

    debounced('value');
    debounced.flush();

    expect(fn).toHaveBeenCalledWith('value');
    vi.advanceTimersByTime(500);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it('flush without pending arguments does nothing', () => {
    const fn = vi.fn();
    const debounced = debounce(fn, 200);

    debounced.flush();
    expect(fn).not.toHaveBeenCalled();
  });

  it('cancel drops the pending call', () => {
    const fn = vi.fn();
    const debounced = debounce(fn, 200);

    debounced('value');
    debounced.cancel();

    vi.advanceTimersByTime(500);
    expect(fn).not.toHaveBeenCalled();
  });
});
