import { useState, useEffect, useRef, useCallback } from 'react'

interface AutoRefreshHook {
  data: any
  isConnected: boolean
  error: string | null
  mode: 'polling' | 'disconnected'
}

const POLLING_INTERVAL = 5000 // 5 seconds

// Use relative URL that works with nginx proxy
const getApiUrl = () => {
  if (typeof window !== 'undefined') {
    // Browser: use relative path (nginx will proxy to /api)
    return '/api'
  }
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
}

const API_URL = getApiUrl()

export default function useAutoRefresh(enabled: boolean = true): AutoRefreshHook {
  const [data, setData] = useState<any>(null)
  const [error, setError] = useState<string | null>(null)
  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null)

  // HTTP polling for data updates
  const fetchData = useCallback(async () => {
    try {
      // API_URL is already '/api' so just append the endpoint
      const endpoint = API_URL.startsWith('/') ? `${API_URL}/gamma/all` : `${API_URL}/api/gamma/all`
      const response = await fetch(endpoint)
      if (response.ok) {
        const result = await response.json()
        setData(result.data || result)
        setError(null)
        return true
      } else {
        setError(`HTTP ${response.status}: ${response.statusText}`)
        return false
      }
    } catch (err) {
      console.error('HTTP polling error:', err)
      setError('HTTP polling failed')
      return false
    }
  }, [])

  // Start HTTP polling
  const startPolling = useCallback(() => {
    // Initial fetch
    fetchData()
    
    // Poll every 5 seconds
    pollingIntervalRef.current = setInterval(() => {
      fetchData()
    }, POLLING_INTERVAL)
  }, [fetchData])

  // Stop HTTP polling
  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
  }, [])

  useEffect(() => {
    if (enabled) {
      startPolling()
    } else {
      stopPolling()
    }

    return () => {
      stopPolling()
    }
  }, [enabled, startPolling, stopPolling])

  return { 
    data, 
    isConnected: enabled, // Show as connected when polling is active
    error, 
    mode: enabled ? 'polling' : 'disconnected'
  }
}
