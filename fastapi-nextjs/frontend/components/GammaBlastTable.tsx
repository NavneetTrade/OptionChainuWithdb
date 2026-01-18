import { useEffect, useState } from 'react'
import axios from 'axios'
import { formatISTTimeAMPM } from '../utils/timeUtils'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface GammaBlastTableProps {
  onSymbolClick: (symbol: string) => void
  liveData: any
}

export default function GammaBlastTable({ onSymbolClick, liveData }: GammaBlastTableProps) {
  const [blasts, setBlasts] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchBlasts()
    const interval = setInterval(fetchBlasts, 30000) // Refresh every 30 seconds
    return () => clearInterval(interval)
  }, [])

  const fetchBlasts = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/top-blasts?limit=15`)
      setBlasts(response.data.top_blasts)
    } catch (error) {
      console.error('Error fetching blasts:', error)
    } finally {
      setLoading(false)
    }
  }

  const getProbabilityBadge = (prob: number) => {
    if (prob >= 0.7) return 'bg-red-600 text-white'
    if (prob >= 0.5) return 'bg-orange-500 text-white'
    if (prob >= 0.3) return 'bg-yellow-500 text-black'
    return 'bg-green-600 text-white'
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12 bg-dark-card rounded-lg">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gamma-blue"></div>
      </div>
    )
  }

  if (blasts.length === 0) {
    return (
      <div className="bg-dark-card rounded-lg p-8 text-center">
        <p className="text-gray-400">No gamma blasts detected</p>
      </div>
    )
  }

  return (
    <div className="bg-dark-card rounded-lg overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-gray-800">
            <tr>
              <th className="px-4 py-3 text-left text-sm font-semibold">Symbol</th>
              <th className="px-4 py-3 text-center text-sm font-semibold">Probability</th>
              <th className="px-4 py-3 text-center text-sm font-semibold">Direction</th>
              <th className="px-4 py-3 text-center text-sm font-semibold">Confidence</th>
              <th className="px-4 py-3 text-right text-sm font-semibold">Net GEX</th>
              <th className="px-4 py-3 text-right text-sm font-semibold">ATM IV</th>
              <th className="px-4 py-3 text-right text-sm font-semibold">OI Velocity</th>
              <th className="px-4 py-3 text-right text-sm font-semibold">Last Update</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-700">
            {blasts.map((blast, idx) => (
              <tr
                key={`${blast.symbol}-${idx}`}
                onClick={() => onSymbolClick(blast.symbol)}
                className="hover:bg-gray-800 cursor-pointer smooth-transition"
              >
                <td className="px-4 py-3 font-semibold">{blast.symbol}</td>
                <td className="px-4 py-3 text-center">
                  <span className={`px-3 py-1 rounded-full text-sm font-semibold ${getProbabilityBadge(blast.probability)}`}>
                    {((blast.probability ?? 0) * 100).toFixed(1)}%
                  </span>
                </td>
                <td className="px-4 py-3 text-center">
                  <span className={`font-semibold ${
                    blast.direction === 'BULLISH' ? 'text-gamma-green' :
                    blast.direction === 'BEARISH' ? 'text-gamma-red' : 'text-gray-400'
                  }`}>
                    {blast.direction === 'BULLISH' ? '📈 Bullish' :
                     blast.direction === 'BEARISH' ? '📉 Bearish' : '➡️ Neutral'}
                  </span>
                </td>
                <td className="px-4 py-3 text-center text-sm">{blast.confidence}</td>
                <td className="px-4 py-3 text-right font-mono text-sm">
                  {((blast.net_gex ?? 0) / 1_000_000).toFixed(2)}M
                </td>
                <td className="px-4 py-3 text-right font-mono text-sm">
                  {(blast.atm_iv ?? 0).toFixed(2)}%
                </td>
                <td className={`px-4 py-3 text-right font-mono text-sm font-semibold ${
                  blast.oi_velocity > 0 ? 'text-gamma-green' : 'text-gamma-red'
                }`}>
                  {blast.oi_velocity > 0 ? '+' : ''}{(blast.oi_velocity ?? 0).toFixed(1)}
                </td>
                <td className="px-4 py-3 text-right text-xs text-gray-400">
                  {formatISTTimeAMPM(blast.timestamp)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
