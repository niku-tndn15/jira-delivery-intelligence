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
  const intervalRef = useRef(null) // Added: Keeps track of our countdown timer

  const run = useCallback(async () => {
    if (!fetcher) return
    
    // Clean up any running requests or timers before starting a new one
    abortRef.current?.abort()
    if (intervalRef.current) clearInterval(intervalRef.current)
    
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setLoading(true)
    setError(null)
    
    try {
      const result = await fetcher()
      if (!ctrl.signal.aborted) setData(result)
    } catch (err) {
      if (!ctrl.signal.aborted) {
        let errorMessage = err.message ?? 'Failed to load'
        
        // Intercept gateway/timeout errors during the massive initial Jira sync
        if (
          errorMessage.includes('502') || 
          errorMessage.toLowerCase().includes('bad gateway') || 
          errorMessage.toLowerCase().includes('network error')
        ) {
          let timeLeft = 180; // 3 minutes in seconds
          
          // Initial message
          setError(`Building Data Warehouse 🚀 | Syncing... Auto-refreshing in ${timeLeft}s`)
          
          // Start the countdown interval
          intervalRef.current = setInterval(() => {
            timeLeft -= 1;
            
            if (timeLeft <= 0) {
              // When the timer hits 0, stop counting and refresh the page automatically
              clearInterval(intervalRef.current);
              window.location.reload(); 
            } else {
              // Update the error text every second with the new time
              setError(`Building Data Warehouse 🚀 | Syncing... Auto-refreshing in ${timeLeft}s`)
            }
          }, 1000);
          
        } else {
          // If it's a normal error, just show it
          setError(errorMessage)
        }
      }
    } finally {
      if (!ctrl.signal.aborted) setLoading(false)
    }
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps

  // Make sure to clean up the timer if the user leaves the page
  useEffect(() => { 
    run() 
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [run])

  return { data, loading, error, refetch: run }
}