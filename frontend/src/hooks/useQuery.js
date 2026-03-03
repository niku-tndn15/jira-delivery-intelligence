import { useState, useEffect, useCallback, useRef } from 'react'

/**
 * Minimal data-fetching hook.
 * Re-fetches whenever `key` changes.
 *
 * @param {Function|null} fetcher  – async function that returns data
 * @param {any}           key      – re-run whenever this value changes
 * @param {any}           [deps]   – additional deps array (optional)
 */
export function useQuery(fetcher, key) {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)
  const abortRef = useRef(null)

  const run = useCallback(async () => {
    if (!fetcher) return
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setLoading(true)
    setError(null)
    try {
      const result = await fetcher()
      if (!ctrl.signal.aborted) setData(result)
    } catch (err) {
      if (!ctrl.signal.aborted) setError(err.message ?? 'Failed to load')
    } finally {
      if (!ctrl.signal.aborted) setLoading(false)
    }
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { run() }, [run])

  return { data, loading, error, refetch: run }
}
