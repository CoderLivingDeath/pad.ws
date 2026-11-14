import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useWorkspace } from '../useWorkspace';

const makeWrapper = () => {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidate };
};

const workspaceState = {
  id: 'workspace-1',
  state: 'running',
  name: 'ubuntu',
  username: 'admin',
  base_url: 'https://coder.example',
  agent: 'main',
};

describe('useWorkspace', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('loads the workspace state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => workspaceState }));
    const { Wrapper } = makeWrapper();

    const { result } = renderHook(() => useWorkspace(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.workspaceState).toEqual(workspaceState));
    expect(result.current.isLoadingState).toBe(false);
    expect(result.current.isStateError).toBe(false);
  });

  it('rejects an unexpected payload', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ unexpected: true }) }),
    );
    const { Wrapper } = makeWrapper();

    const { result } = renderHook(() => useWorkspace(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isStateError).toBe(true));
    expect(result.current.stateError?.message).toContain('Invalid data structure');
  });

  it('surfaces the server error detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({ detail: 'coder unavailable' }),
      }),
    );
    const { Wrapper } = makeWrapper();

    const { result } = renderHook(() => useWorkspace(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isStateError).toBe(true));
    expect(result.current.stateError?.message).toBe('coder unavailable');
  });

  it('falls back to the status code when the error body is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => {
          throw new Error('not json');
        },
      }),
    );
    const { Wrapper } = makeWrapper();

    const { result } = renderHook(() => useWorkspace(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isStateError).toBe(true));
    expect(result.current.stateError?.message).toContain('Status: 500');
  });

  it('starts the workspace and refreshes the state', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => workspaceState })
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    vi.stubGlobal('fetch', fetchMock);
    const { Wrapper, invalidate } = makeWrapper();

    const { result } = renderHook(() => useWorkspace(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.workspaceState).toEqual(workspaceState));

    await act(async () => {
      result.current.startWorkspace();
      await waitFor(() => expect(result.current.isStarting).toBe(false));
    });

    expect(fetchMock).toHaveBeenCalledWith('/api/workspace/start', { method: 'POST' });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['workspaceState'] });
  });

  it('reports a start failure', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => workspaceState })
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'start failed' }),
      });
    vi.stubGlobal('fetch', fetchMock);
    const { Wrapper } = makeWrapper();

    const { result } = renderHook(() => useWorkspace(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.workspaceState).toEqual(workspaceState));

    await act(async () => {
      result.current.startWorkspace();
    });

    await waitFor(() => expect(result.current.isStartError).toBe(true));
    expect(result.current.startError?.message).toBe('start failed');
  });

  it('stops the workspace and refreshes the state', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => workspaceState })
      .mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    vi.stubGlobal('fetch', fetchMock);
    const { Wrapper, invalidate } = makeWrapper();

    const { result } = renderHook(() => useWorkspace(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.workspaceState).toEqual(workspaceState));

    await act(async () => {
      result.current.stopWorkspace();
      await waitFor(() => expect(result.current.isStopping).toBe(false));
    });

    expect(fetchMock).toHaveBeenCalledWith('/api/workspace/stop', { method: 'POST' });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['workspaceState'] });
  });

  it('reports a stop failure', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => workspaceState })
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({ detail: 'stop failed' }),
      });
    vi.stubGlobal('fetch', fetchMock);
    const { Wrapper } = makeWrapper();

    const { result } = renderHook(() => useWorkspace(), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.workspaceState).toEqual(workspaceState));

    await act(async () => {
      result.current.stopWorkspace();
    });

    await waitFor(() => expect(result.current.isStopError).toBe(true));
    expect(result.current.stopError?.message).toBe('stop failed');
  });
});
