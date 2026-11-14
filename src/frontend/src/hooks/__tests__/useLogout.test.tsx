import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useLogout } from '../useLogout';

const makeWrapper = () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidate };
};

describe('useLogout', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('logs out and invalidates the auth status query', async () => {
    const body = {
      status: 'ok',
      logout_url: 'https://auth.example/logout',
      coder_logout_url: 'https://coder.example/logout',
    };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => body }));
    const { Wrapper, invalidate } = makeWrapper();

    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });
    await act(async () => {
      const data = await result.current.mutateAsync();
      expect(data).toEqual(body);
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(fetch).toHaveBeenCalledWith('/api/auth/logout', {
      method: 'GET',
      credentials: 'include',
    });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['authStatus'] });
  });

  it('surfaces the server error detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'logout backend down' }),
      }),
    );
    const { Wrapper } = makeWrapper();

    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });
    await act(async () => {
      await expect(result.current.mutateAsync()).rejects.toThrow('logout backend down');
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it('falls back to the status code when the error body is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 502,
        json: async () => {
          throw new Error('not json');
        },
      }),
    );
    const { Wrapper } = makeWrapper();

    const { result } = renderHook(() => useLogout(), { wrapper: Wrapper });
    await act(async () => {
      await expect(result.current.mutateAsync()).rejects.toThrow('Logout failed with status: 502');
    });
  });
});
