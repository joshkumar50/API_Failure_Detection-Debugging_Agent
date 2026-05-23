import { useEffect, useRef, useState } from 'react';

/**
 * Generic polling hook — calls `fetcher()` every `intervalMs` milliseconds.
 * Pauses when `enabled` is false. Returns data, loading, and error state.
 */
export function usePolling<T>(
  fetcher: () => Promise<T | null>,
  intervalMs: number,
  enabled: boolean = true
): { data: T | null; loading: boolean; error: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const fetcherRef = useRef(fetcher);

  // Keep fetcher ref up-to-date without re-running effect
  useEffect(() => {
    fetcherRef.current = fetcher;
  }, [fetcher]);

  useEffect(() => {
    if (!enabled) return;

    let mounted = true;

    const poll = async () => {
      try {
        const result = await fetcherRef.current();
        if (!mounted) return;
        if (result !== null) {
          setData(result);
          setError(false);
        } else {
          setError(true);
        }
      } catch {
        if (mounted) setError(true);
      } finally {
        if (mounted) setLoading(false);
      }
    };

    // Initial fetch
    poll();

    // Set up interval
    const id = setInterval(poll, intervalMs);

    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [intervalMs, enabled]);

  return { data, loading, error };
}
