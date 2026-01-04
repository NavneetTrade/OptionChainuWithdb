import { useState, useEffect } from 'react'
import axios from 'axios'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, BarChart, Bar } from 'recharts'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface ITMData {
  symbol: string
  expiry: string
  itm_count: number
  hours: number
  data_points: number
  latest: {
    timestamp: string
    itm_count: number
    ce_oi: number
    pe_oi: number
    ce_volume: number
    pe_volume: number
    ce_chgoi: number
    pe_chgoi: number
    spot_price: number
  }
  history: Array<{
    timestamp: string
    itm_count: number
    ce_oi: number
    pe_oi: number
    ce_volume: number
    pe_volume: number
    ce_chgoi: number
    pe_chgoi: number
    spot_price: number
  }>
  summary: {
    avg_ce_oi: number
    avg_pe_oi: number
    max_ce_oi: number
    max_pe_oi: number
  }
}

export default function ITMAnalysis() {
  const [symbol, setSymbol] = useState('NIFTY')
  const [expiry, setExpiry] = useState('')
  const [itmCount, setItmCount] = useState(1)
  const [hours, setHours] = useState(24)
  const [data, setData] = useState<ITMData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [availableExpiries, setAvailableExpiries] = useState<string[]>([])

  const symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX']
  const itmCounts = [1, 2, 3, 4, 5]
  const hoursOptions = [4, 8, 24, 48, 72]

  useEffect(() => {
    // Fetch available expiries when symbol changes
    fetchExpiries()
  }, [symbol])

  useEffect(() => {
    if (expiry) {
      fetchITMData()
    }
  }, [symbol, expiry, itmCount, hours])

  const fetchExpiries = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/expiries/${symbol}`)
      const expiries = response.data.itm_expiries || []
      setAvailableExpiries(expiries)
      
      // Auto-select first available expiry
      if (expiries.length > 0) {
        setExpiry(expiries[0])
      } else {
        setExpiry('')
        setError(`No expiry data found for ${symbol}. Please ensure background service is running.`)
      }
    } catch (err: any) {
      console.error('Error fetching expiries:', err)
      // Fallback: try to set a default expiry
      const today = new Date()
      const nextThursday = new Date(today)
      nextThursday.setDate(today.getDate() + ((4 - today.getDay() + 7) % 7 || 7))
      setExpiry(nextThursday.toISOString().split('T')[0])
    }
  }

  const fetchITMData = async () => {
    if (!expiry) return
    
    setLoading(true)
    setError(null)
    try {
      const response = await axios.get<ITMData>(
        `${API_URL}/api/itm/${symbol}?expiry=${expiry}&itm_count=${itmCount}&hours=${hours}`
      )
      setData(response.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch ITM data')
    } finally {
      setLoading(false)
    }
  }

  const formatChartData = (type: 'oi' | 'volume' | 'chgoi') => {
    if (!data) return []
    return data.history.map(item => ({
      time: new Date(item.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
      timestamp: item.timestamp,
      call: type === 'oi' ? item.ce_oi : type === 'volume' ? item.ce_volume : item.ce_chgoi,
      put: type === 'oi' ? item.pe_oi : type === 'volume' ? item.pe_volume : item.pe_chgoi,
      spot: item.spot_price
    }))
  }

  const formatNumber = (num: number) => {
    if (num >= 10000000) return `${(num / 10000000).toFixed(2)}Cr`
    if (num >= 100000) return `${(num / 100000).toFixed(2)}L`
    if (num >= 1000) return `${(num / 1000).toFixed(2)}K`
    return num.toFixed(0)
  }

  return (
    <div className="space-y-6">
      {/* Header Controls */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div>
          <label className="block text-sm text-gray-400 mb-2">Symbol</label>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-full bg-dark-card border border-gray-700 rounded-lg px-4 py-2 text-white"
          >
            {symbols.map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        
        <div>
          <label className="block text-sm text-gray-400 mb-2">Expiry Date</label>
          <select
            value={expiry}
            onChange={(e) => setExpiry(e.target.value)}
            className="w-full bg-dark-card border border-gray-700 rounded-lg px-4 py-2 text-white"
          >
            {availableExpiries.length > 0 ? (
              availableExpiries.map(exp => (
                <option key={exp} value={exp}>
                  {new Date(exp).toLocaleDateString('en-US', { 
                    year: 'numeric', 
                    month: 'short', 
                    day: 'numeric' 
                  })}
                </option>
              ))
            ) : (
              <option value="">No expiries available</option>
            )}
          </select>
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-2">ITM Strikes</label>
          <select
            value={itmCount}
            onChange={(e) => setItmCount(Number(e.target.value))}
            className="w-full bg-dark-card border border-gray-700 rounded-lg px-4 py-2 text-white"
          >
            {itmCounts.map(count => (
              <option key={count} value={count}>{count}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-2">Look Back (hrs)</label>
          <select
            value={hours}
            onChange={(e) => setHours(Number(e.target.value))}
            className="w-full bg-dark-card border border-gray-700 rounded-lg px-4 py-2 text-white"
          >
            {hoursOptions.map(h => (
              <option key={h} value={h}>{h}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Info Banner */}
      <div className="bg-blue-900/20 border border-blue-500/30 rounded-lg p-4">
        <p className="text-sm text-blue-300">
          📊 ITM Analysis shows {itmCount} strike{itmCount > 1 ? 's' : ''} closest to ATM for {symbol} | 
          Expiry: {expiry} | Showing last {hours} hours of data
        </p>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto"></div>
          <p className="text-gray-400 mt-4">Loading ITM data...</p>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-900/20 border border-red-500 rounded-lg p-4">
          <p className="text-red-400">⚠️ {error}</p>
          <p className="text-gray-400 text-sm mt-2">
            Tip: Try increasing the "Look Back" hours to 48 or 72 to see previous session data
          </p>
        </div>
      )}

      {/* Data Display */}
      {!loading && !error && data && (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-dark-card rounded-lg border border-gray-800 p-4">
              <div className="text-sm text-gray-400 mb-2">Data Points</div>
              <div className="text-3xl font-bold">{data.data_points}</div>
            </div>
            <div className="bg-dark-card rounded-lg border border-gray-800 p-4">
              <div className="text-sm text-gray-400 mb-2">Avg Call OI</div>
              <div className="text-2xl font-bold text-gamma-red">{formatNumber(data.summary.avg_ce_oi)}</div>
            </div>
            <div className="bg-dark-card rounded-lg border border-gray-800 p-4">
              <div className="text-sm text-gray-400 mb-2">Avg Put OI</div>
              <div className="text-2xl font-bold text-gamma-green">{formatNumber(data.summary.avg_pe_oi)}</div>
            </div>
            <div className="bg-dark-card rounded-lg border border-gray-800 p-4">
              <div className="text-sm text-gray-400 mb-2">Latest Spot</div>
              <div className="text-2xl font-bold">{data.latest?.spot_price.toFixed(2)}</div>
            </div>
          </div>

          {/* ITM Open Interest Chart */}
          <div className="bg-dark-card rounded-xl border border-gray-800 p-6">
            <h3 className="text-xl font-semibold mb-4">
              📊 ITM Open Interest - {itmCount} Strike{itmCount > 1 ? 's' : ''}
            </h3>
            <ResponsiveContainer width="100%" height={350}>
              <LineChart data={formatChartData('oi')}>
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
                  dataKey="call"
                  stroke="#EF4444"
                  strokeWidth={2}
                  name="Call OI"
                  dot={{ fill: '#EF4444' }}
                />
                <Line
                  type="monotone"
                  dataKey="put"
                  stroke="#10B981"
                  strokeWidth={2}
                  name="Put OI"
                  dot={{ fill: '#10B981' }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* ITM Volume Chart */}
          <div className="bg-dark-card rounded-xl border border-gray-800 p-6">
            <h3 className="text-xl font-semibold mb-4">
              📈 ITM Volume - {itmCount} Strike{itmCount > 1 ? 's' : ''}
            </h3>
            <ResponsiveContainer width="100%" height={350}>
              <LineChart data={formatChartData('volume')}>
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
                  dataKey="call"
                  stroke="#F59E0B"
                  strokeWidth={2}
                  name="Call Volume"
                  dot={{ fill: '#F59E0B' }}
                />
                <Line
                  type="monotone"
                  dataKey="put"
                  stroke="#3B82F6"
                  strokeWidth={2}
                  name="Put Volume"
                  dot={{ fill: '#3B82F6' }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* ITM Change in OI Chart */}
          <div className="bg-dark-card rounded-xl border border-gray-800 p-6">
            <h3 className="text-xl font-semibold mb-4">
              🔄 ITM Change in OI - {itmCount} Strike{itmCount > 1 ? 's' : ''}
            </h3>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={formatChartData('chgoi')}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="time" stroke="#9CA3AF" />
                <YAxis stroke="#9CA3AF" />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                  labelStyle={{ color: '#F3F4F6' }}
                />
                <Legend />
                <Bar dataKey="call" fill="#EF4444" name="Call Chg OI" />
                <Bar dataKey="put" fill="#10B981" name="Put Chg OI" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  )
}
