import { useState, useEffect } from 'react'
import axios from 'axios'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { formatISTTimeForChart } from '../utils/timeUtils'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface SentimentData {
  symbol: string
  current: {
    timestamp: string
    sentiment_score: number
    sentiment: string
    confidence: string
    spot_price: number
    pcr_oi: number
    pcr_chgoi: number
    pcr_volume: number
  }
  history: Array<{
    timestamp: string
    sentiment_score: number
    sentiment: string
    confidence: string
    spot_price: number
    pcr_oi: number
    pcr_chgoi: number
    pcr_volume: number
  }>
  data_points: number
}

export default function SentimentDashboard() {
  const [symbol, setSymbol] = useState('NIFTY')
  const [hours, setHours] = useState(4)
  const [data, setData] = useState<SentimentData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX']
  const timeRanges = [
    { label: 'Last Hour', value: 1 },
    { label: 'Last 4 Hours', value: 4 },
    { label: 'Last 24 Hours', value: 24 },
    { label: 'All Data (7 days)', value: 168 }
  ]

  useEffect(() => {
    fetchSentimentData()
  }, [symbol, hours])

  const fetchSentimentData = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await axios.get<SentimentData>(`${API_URL}/api/sentiment/${symbol}?hours=${hours}`)
      setData(response.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch sentiment data')
    } finally {
      setLoading(false)
    }
  }

  const getSentimentColor = (sentiment: string) => {
    switch (sentiment) {
      case 'STRONG BULLISH': return 'text-green-400 bg-green-500/20'
      case 'BULLISH': return 'text-green-300 bg-green-500/15'
      case 'BULLISH BIAS': return 'text-green-200 bg-green-500/10'
      case 'STRONG BEARISH': return 'text-red-400 bg-red-500/20'
      case 'BEARISH': return 'text-red-300 bg-red-500/15'
      case 'BEARISH BIAS': return 'text-red-200 bg-red-500/10'
      default: return 'text-gray-300 bg-gray-500/10'
    }
  }

  const getConfidenceColor = (confidence: string) => {
    switch (confidence) {
      case 'HIGH': return 'text-blue-400'
      case 'MEDIUM': return 'text-yellow-400'
      case 'LOW': return 'text-gray-400'
      default: return 'text-gray-400'
    }
  }

  const formatChartData = () => {
    if (!data) return []
    return data.history.map(item => ({
      time: formatISTTimeForChart(item.timestamp),
      score: item.sentiment_score,
      pcr_oi: item.pcr_oi,
      pcr_volume: item.pcr_volume,
      spot: item.spot_price
    }))
  }

  return (
    <div className="space-y-6">
      {/* Header Controls */}
      <div className="flex flex-wrap gap-4 items-center justify-between">
        <div className="flex gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-2">Symbol</label>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="bg-dark-card border border-gray-700 rounded-lg px-4 py-2 text-white"
            >
              {symbols.map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Time Range</label>
            <select
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
              className="bg-dark-card border border-gray-700 rounded-lg px-4 py-2 text-white"
            >
              {timeRanges.map(tr => (
                <option key={tr.value} value={tr.value}>{tr.label}</option>
              ))}
            </select>
          </div>
        </div>
        <button
          onClick={fetchSentimentData}
          className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg transition-colors"
        >
          🔄 Refresh
        </button>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto"></div>
          <p className="text-gray-400 mt-4">Loading sentiment data...</p>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-900/20 border border-red-500 rounded-lg p-4">
          <p className="text-red-400">⚠️ {error}</p>
        </div>
      )}

      {/* Data Display */}
      {!loading && !error && data && (
        <>
          {/* Current Sentiment Card */}
          <div className="bg-dark-card rounded-xl border border-gray-800 p-6">
            <h3 className="text-xl font-semibold mb-6">Current Sentiment - {symbol}</h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Sentiment */}
              <div className="bg-dark-bg rounded-lg p-4">
                <div className="text-sm text-gray-400 mb-2">Sentiment</div>
                <div className={`text-lg font-bold px-3 py-1 rounded inline-block ${getSentimentColor(data.current.sentiment)}`}>
                  {data.current.sentiment}
                </div>
                <div className={`text-sm mt-2 ${getConfidenceColor(data.current.confidence)}`}>
                  Confidence: {data.current.confidence}
                </div>
              </div>

              {/* Score */}
              <div className="bg-dark-bg rounded-lg p-4">
                <div className="text-sm text-gray-400 mb-2">Sentiment Score</div>
                <div className="text-3xl font-bold">
                  {data.current.sentiment_score.toFixed(2)}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  Range: -100 to +100
                </div>
              </div>

              {/* Spot Price */}
              <div className="bg-dark-bg rounded-lg p-4">
                <div className="text-sm text-gray-400 mb-2">Spot Price</div>
                <div className="text-2xl font-bold">
                  {data.current.spot_price.toFixed(2)}
                </div>
              </div>

              {/* Data Points */}
              <div className="bg-dark-bg rounded-lg p-4">
                <div className="text-sm text-gray-400 mb-2">Data Points</div>
                <div className="text-2xl font-bold">
                  {data.data_points}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  Last {hours} hour{hours > 1 ? 's' : ''}
                </div>
              </div>
            </div>

            {/* PCR Ratios */}
            <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-dark-bg rounded-lg p-4">
                <div className="text-sm text-gray-400 mb-2">PCR - OI</div>
                <div className="text-xl font-bold">{data.current.pcr_oi.toFixed(3)}</div>
                <div className="text-xs text-gray-500 mt-1">Put/Call Ratio (Open Interest)</div>
              </div>
              <div className="bg-dark-bg rounded-lg p-4">
                <div className="text-sm text-gray-400 mb-2">PCR - Volume</div>
                <div className="text-xl font-bold">{data.current.pcr_volume.toFixed(3)}</div>
                <div className="text-xs text-gray-500 mt-1">Put/Call Ratio (Volume)</div>
              </div>
              <div className="bg-dark-bg rounded-lg p-4">
                <div className="text-sm text-gray-400 mb-2">PCR - Change OI</div>
                <div className="text-xl font-bold">{data.current.pcr_chgoi.toFixed(3)}</div>
                <div className="text-xs text-gray-500 mt-1">Put/Call Ratio (Change in OI)</div>
              </div>
            </div>
          </div>

          {/* Sentiment Trend Chart */}
          {data.history.length > 1 && (
            <div className="bg-dark-card rounded-xl border border-gray-800 p-6">
              <h3 className="text-xl font-semibold mb-4">Sentiment Trend</h3>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={formatChartData()}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis dataKey="time" stroke="#9CA3AF" />
                  <YAxis stroke="#9CA3AF" />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                    labelStyle={{ color: '#F3F4F6' }}
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="score"
                    stroke="#3B82F6"
                    strokeWidth={2}
                    name="Sentiment Score"
                    dot={{ fill: '#3B82F6' }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* PCR Trend Chart */}
          {data.history.length > 1 && (
            <div className="bg-dark-card rounded-xl border border-gray-800 p-6">
              <h3 className="text-xl font-semibold mb-4">PCR Ratios Trend</h3>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={formatChartData()}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                  <XAxis dataKey="time" stroke="#9CA3AF" />
                  <YAxis stroke="#9CA3AF" />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                    labelStyle={{ color: '#F3F4F6' }}
                  />
                  <Legend />
                  <Line
                    type="monotone"
                    dataKey="pcr_oi"
                    stroke="#10B981"
                    strokeWidth={2}
                    name="PCR OI"
                    dot={{ fill: '#10B981' }}
                  />
                  <Line
                    type="monotone"
                    dataKey="pcr_volume"
                    stroke="#F59E0B"
                    strokeWidth={2}
                    name="PCR Volume"
                    dot={{ fill: '#F59E0B' }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}
    </div>
  )
}
