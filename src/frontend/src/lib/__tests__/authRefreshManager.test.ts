import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  AUTH_STATUS_KEY,
  cancelTokenRefresh,
  scheduleTokenRefresh,
} from '../authRefreshManager';

describe('authRefreshManager', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    cancelTokenRefresh();
  });

  afterEach(() => {
    cancelTokenRefresh();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('refreshes five minutes before expiry', async () => {
    const payload = { authenticated: true, expires_in: 1200 };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => payload });
    vi.stubGlobal('fetch', fetchMock);
    const onRefresh = vi.fn();
    const onError = vi.fn();

    scheduleTokenRefresh(600, onRefresh, onError);
    expect(fetchMock).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(5 * 60 * 1000);

    expect(fetchMock).toHaveBeenCalledWith('/api/auth/refresh', {
      method: 'POST',
      credentials: 'include',
    });
    expect(onRefresh).toHaveBeenCalledWith(payload);
    expect(onError).not.toHaveBeenCalled();
  });

  it('schedules only one refresh at a time', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ authenticated: true }),
    });
    vi.stubGlobal('fetch', fetchMock);
    const onRefresh = vi.fn();

    scheduleTokenRefresh(600, onRefresh, vi.fn());
    scheduleTokenRefresh(600, onRefresh, vi.fn());

    await vi.advanceTimersByTimeAsync(5 * 60 * 1000);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('does not schedule when the token expires too soon', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    scheduleTokenRefresh(120, vi.fn(), vi.fn());

    vi.advanceTimersByTime(10 * 60 * 1000);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('reports refresh failures through onError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({}) }),
    );
    const onRefresh = vi.fn();
    const onError = vi.fn();

    scheduleTokenRefresh(600, onRefresh, onError);
    await vi.advanceTimersByTimeAsync(5 * 60 * 1000);

    expect(onRefresh).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0][0]).toBeInstanceOf(Error);
  });

  it('cancels a scheduled refresh', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal('fetch', fetchMock);
    const onRefresh = vi.fn();

    scheduleTokenRefresh(600, onRefresh, vi.fn());
    cancelTokenRefresh();

    await vi.advanceTimersByTimeAsync(10 * 60 * 1000);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(onRefresh).not.toHaveBeenCalled();
  });

  it('exposes a stable auth status query key', () => {
    expect(AUTH_STATUS_KEY).toBe('authStatus');
  });
});
