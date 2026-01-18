import { useEffect, useState } from 'react'
import axios from 'axios'
import { formatISTTimeAMPM } from '../utils/timeUtils'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface IndicesOverviewProps {
  onSymbolClick: (symbol: string) => void
  selectedSymbol: string | null
  liveData: any
}

export default function IndicesOverview({ onSymbolClick, selectedSymbol, liveData }: IndicesOverviewProps) {
  const [indices, setIndices] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchIndices()
  }, [])

  // Update with live data
  useEffect(() => {
    if (liveData && Array.isArray(liveData)) {
      const indexSymbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX']
      const indexData = liveData.filter(d => indexSymbols.includes(d.symbol))
      if (indexData.length > 0) {
        setIndices(indexData)
      }
    }
  }, [liveData])

  const fetchIndices = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/indices`)
      setIndices(response.data.indices)
    } catch (error) {
      console.error('Error fetching indices:', error)
    } finally {
      setLoading(false)
    }
  }

  const getDirectionColor = (direction: string) => {
    if (direction === 'BULLISH') return 'text-gamma-green'
    if (direction === 'BEARISH') return 'text-gamma-red'
    return 'text-gray-400'
  }

  const getDirectionIcon = (direction: string) => {
    if (direction === 'BULLISH') return '📈'
    if (direction === 'BEARISH') return '📉'
    return '➡️'
  }

  const getBlastColor = (prob: number) => {
    if (prob >= 0.7) return 'bg-red-500'
    if (prob >= 0.5) return 'bg-orange-500'
    if (prob >= 0.3) return 'bg-yellow-500'
    return 'bg-green-500'
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12 bg-dark-card rounded-lg">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gamma-blue"></div>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
      {indices.map((index) => (
        <div
          key={index.symbol}
          onClick={() => onSymbolClick(index.symbol)}
          className={`
            bg-dark-card rounded-lg p-4 cursor-pointer 
            smooth-transition hover:shadow-lg hover:scale-105
            ${selectedSymbol === index.symbol ? 'ring-2 ring-gamma-blue' : ''}
          `}
        >
          {/* Symbol Name */}
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-lg font-bold">{index.symbol}</h3>
            <div className={`text-2xl ${getDirectionColor(index.predicted_direction)}`}>
              {getDirectionIcon(index.predicted_direction)}
            </div>
          </div>

          {/* Gamma Blast Probability */}
          <div className="mb-3">
            <div className="flex items-center justify-between text-sm mb-1">
              <span className="text-gray-400">Blast Probability</span>
              <span className="font-semibold">{((index.gamma_blast_probability ?? 0) * 100).toFixed(1)}%</span>
            </div>
            <div className="w-full bg-gray-700 rounded-full h-2">
              <div
                className={`h-2 rounded-full ${getBlastColor(index.gamma_blast_probability)}`}
                style={{ width: `${(index?.gamma_blast_probability ?? 0) * 100}%` }}
              />
            </div>
          </div>

          {/* Metrics Grid */}
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-gray-400">GEX:</span>
              <span className="ml-1 font-mono">
                {((index.net_gex ?? 0) / 1_000_000).toFixed(1)}M
              </span>
            </div>
            <div>
              <span className="text-gray-400">IV:</span>
              <span className="ml-1 font-mono">{(index.atm_iv ?? 0).toFixed(2)}%</span>
            </div>
            <div>
              <span className="text-gray-400">OI Vel:</span>
              <span className={`ml-1 font-mono ${index.oi_velocity > 0 ? 'text-gamma-green' : 'text-gamma-red'}`}>
                {index.oi_velocity > 0 ? '+' : ''}{(index.oi_velocity ?? 0).toFixed(1)}
              </span>
            </div>
            <div>
              <span className="text-gray-400">IV Vel:</span>
              <span className={`ml-1 font-mono ${index.iv_velocity > 0 ? 'text-gamma-green' : 'text-gamma-red'}`}>
                {index.iv_velocity > 0 ? '+' : ''}{((index.iv_velocity ?? 0) * 100).toFixed(2)}%
              </span>
            </div>
          </div>

          {/* Timestamp */}
          <div className="mt-3 pt-2 border-t border-gray-700">
            <span className="text-xs text-gray-500">
              {formatISTTimeAMPM(index.timestamp)}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}
