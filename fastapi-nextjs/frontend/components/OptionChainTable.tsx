import { useState, useEffect } from 'react'
import axios from 'axios'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Strike {
  strike: number
  is_atm: boolean
  call: {
    ltp: number
    change: number
    oi: number
    chg_oi: number
    volume: number
    iv: number
    delta: number
    gamma: number
    theta: number
    vega: number
    position: string
  }
  put: {
    ltp: number
    change: number
    oi: number
    chg_oi: number
    volume: number
    iv: number
    delta: number
    gamma: number
    theta: number
    vega: number
    position: string
  }
}

interface OptionChainData {
  symbol: string
  expiry: string
  spot_price: number
  timestamp: string
  strikes: Strike[]
  pcr: {
    oi: number
    volume: number
    chg_oi: number
  }
  totals: {
    ce_oi: number
    pe_oi: number
    ce_volume: number
    pe_volume: number
  }
}

export default function OptionChainTable() {
  const [symbol, setSymbol] = useState('NIFTY')
  const [expiry, setExpiry] = useState('')
  const [availableExpiries, setAvailableExpiries] = useState<string[]>([])
  const [data, setData] = useState<OptionChainData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX']

  useEffect(() => {
    fetchExpiries()
  }, [symbol])

  useEffect(() => {
    if (expiry) {
      fetchOptionChain()
    }
  }, [symbol, expiry])

  const fetchExpiries = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/expiries/${symbol}`)
      const expiries = response.data.option_chain_expiries || []
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
      setError('Failed to fetch available expiries')
    }
  }

  const fetchOptionChain = async () => {
    if (!expiry) return
    
    setLoading(true)
    setError(null)
    try {
      const response = await axios.get<OptionChainData>(`${API_URL}/api/option-chain/${symbol}?expiry=${expiry}`)
      setData(response.data)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch option chain data')
    } finally {
      setLoading(false)
    }
  }

  const formatNumber = (num: number) => {
    if (num >= 10000000) return `${(num / 10000000).toFixed(2)}Cr`
    if (num >= 100000) return `${(num / 100000).toFixed(2)}L`
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
    return num.toFixed(0)
  }

  const getPositionColor = (position: string) => {
    const colors: Record<string, string> = {
      'Long Build': 'bg-green-500/20 text-green-300 border border-green-500/30',
      'Long Unwinding': 'bg-red-500/20 text-red-300 border border-red-500/30',
      'Short Buildup': 'bg-red-600/20 text-red-300 border border-red-600/30',
      'Short Covering': 'bg-blue-500/20 text-blue-300 border border-blue-500/30',
      'Fresh Positions': 'bg-purple-500/20 text-purple-300 border border-purple-500/30',
      'Position Unwinding': 'bg-orange-500/20 text-orange-300 border border-orange-500/30',
      'Mixed Activity': 'bg-gray-500/20 text-gray-300 border border-gray-500/30',
      'No Change': 'bg-gray-600/20 text-gray-400 border border-gray-600/30'
    }
    return colors[position] || 'bg-gray-500/20 text-gray-300 border border-gray-500/30'
  }

  return (
    <div className="space-y-6">
      {/* Header Controls */}
      <div className="flex flex-wrap gap-4 items-center justify-between">
        <div className="flex gap-4 items-end">
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
            <label className="block text-sm text-gray-400 mb-2">Expiry</label>
            <select
              value={expiry}
              onChange={(e) => setExpiry(e.target.value)}
              className="bg-dark-card border border-gray-700 rounded-lg px-4 py-2 text-white min-w-[150px]"
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
          {data && (
            <div className="text-sm">
              <div className="text-gray-400">Spot Price</div>
              <div className="text-2xl font-bold">{data.spot_price.toFixed(2)}</div>
            </div>
          )}
        </div>
        <button
          onClick={fetchOptionChain}
          disabled={!expiry}
          className="bg-blue-600 hover:bg-blue-700 px-4 py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          🔄 Refresh
        </button>
      </div>

      {/* PCR Summary Cards */}
      {data && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-dark-card rounded-lg border border-gray-800 p-4">
            <div className="text-sm text-gray-400 mb-2">PCR - Open Interest</div>
            <div className="text-3xl font-bold">{data.pcr.oi.toFixed(3)}</div>
            <div className="text-xs text-gray-500 mt-1">
              Put OI: {formatNumber(data.totals.pe_oi)} | Call OI: {formatNumber(data.totals.ce_oi)}
            </div>
          </div>
          <div className="bg-dark-card rounded-lg border border-gray-800 p-4">
            <div className="text-sm text-gray-400 mb-2">PCR - Volume</div>
            <div className="text-3xl font-bold">{data.pcr.volume.toFixed(3)}</div>
            <div className="text-xs text-gray-500 mt-1">
              Put Vol: {formatNumber(data.totals.pe_volume)} | Call Vol: {formatNumber(data.totals.ce_volume)}
            </div>
          </div>
          <div className="bg-dark-card rounded-lg border border-gray-800 p-4">
            <div className="text-sm text-gray-400 mb-2">PCR - Change in OI</div>
            <div className="text-3xl font-bold">{data.pcr.chg_oi.toFixed(3)}</div>
            <div className="text-xs text-gray-500 mt-1">Put/Call Ratio for ΔOI</div>
          </div>
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div className="text-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto"></div>
          <p className="text-gray-400 mt-4">Loading option chain...</p>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-900/20 border border-red-500 rounded-lg p-4">
          <p className="text-red-400">⚠️ {error}</p>
        </div>
      )}

      {/* Option Chain Table */}
      {!loading && !error && data && (
        <div className="bg-black rounded-xl border border-gray-700 overflow-hidden shadow-lg" style={{backgroundColor: '#000'}}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" style={{backgroundColor: '#000'}}>
              <thead className="bg-gray-900 border-b border-gray-700" style={{backgroundColor: '#1a1a1a'}}>
                <tr>
                  {/* Call Side Headers */}
                  <th className="px-3 py-3 text-left text-gray-300 font-semibold" style={{backgroundColor: '#1a1a1a'}}>OI</th>
                  <th className="px-3 py-3 text-left text-gray-300 font-semibold" style={{backgroundColor: '#1a1a1a'}}>CHGOI</th>
                  <th className="px-3 py-3 text-left text-gray-300 font-semibold" style={{backgroundColor: '#1a1a1a'}}>VOLUME</th>
                  <th className="px-3 py-3 text-left text-gray-300 font-semibold" style={{backgroundColor: '#1a1a1a'}}>IV</th>
                  <th className="px-3 py-3 text-left text-gray-300 font-semibold" style={{backgroundColor: '#1a1a1a'}}>LTP</th>
                  <th className="px-3 py-3 text-left text-gray-300 font-semibold" style={{backgroundColor: '#1a1a1a'}}>POSITION</th>
                  
                  {/* Strike */}
                  <th className="px-4 py-3 text-center text-white font-bold bg-gray-700" style={{backgroundColor: '#333'}}>STRIKE</th>
                  
                  {/* Put Side Headers */}
                  <th className="px-3 py-3 text-right text-gray-300 font-semibold" style={{backgroundColor: '#1a1a1a'}}>POSITION</th>
                  <th className="px-3 py-3 text-right text-gray-300 font-semibold" style={{backgroundColor: '#1a1a1a'}}>LTP</th>
                  <th className="px-3 py-3 text-right text-gray-300 font-semibold" style={{backgroundColor: '#1a1a1a'}}>IV</th>
                  <th className="px-3 py-3 text-right text-gray-300 font-semibold" style={{backgroundColor: '#1a1a1a'}}>VOLUME</th>
                  <th className="px-3 py-3 text-right text-gray-300 font-semibold" style={{backgroundColor: '#1a1a1a'}}>CHGOI</th>
                  <th className="px-3 py-3 text-right text-gray-300 font-semibold" style={{backgroundColor: '#1a1a1a'}}>OI</th>
                </tr>
              </thead>
              <tbody style={{backgroundColor: '#000'}}>
                {data.strikes.map((strike, idx) => (
                  <tr
                    key={idx}
                    className={`border-b border-gray-800 hover:bg-gray-900 transition-colors ${
                      strike.is_atm ? 'bg-blue-900/30' : 'bg-black'
                    }`}
                    style={{backgroundColor: strike.is_atm ? '#1e3a5f' : '#000'}}
                  >
                    {/* Call Side Data */}
                    <td className="px-3 py-2 text-white font-semibold" style={{backgroundColor: strike.is_atm ? '#1e3a5f' : '#000'}}>{formatNumber(strike.call.oi)}</td>
                    <td className={`px-3 py-2 font-semibold ${strike.call.chg_oi > 0 ? 'text-green-400' : strike.call.chg_oi < 0 ? 'text-red-400' : 'text-gray-400'}`} style={{backgroundColor: strike.is_atm ? '#1e3a5f' : '#000'}}>
                      {strike.call.chg_oi > 0 ? '+' : ''}{formatNumber(strike.call.chg_oi)}
                    </td>
                    <td className="px-3 py-2 text-gray-200" style={{backgroundColor: strike.is_atm ? '#1e3a5f' : '#000'}}>{formatNumber(strike.call.volume)}</td>
                    <td className="px-3 py-2 text-gray-200" style={{backgroundColor: strike.is_atm ? '#1e3a5f' : '#000'}}>{strike.call.iv.toFixed(2)}</td>
                    <td className="px-3 py-2 font-bold text-white" style={{backgroundColor: strike.is_atm ? '#1e3a5f' : '#000'}}>{strike.call.ltp.toFixed(2)}</td>
                    <td className="px-3 py-2" style={{backgroundColor: strike.is_atm ? '#1e3a5f' : '#000'}}>
                      <span className={`text-xs px-2 py-1 rounded font-semibold ${getPositionColor(strike.call.position)}`}>
                        {strike.call.position}
                      </span>
                    </td>
                    
                    {/* Strike Price */}
                    <td className={`px-4 py-2 text-center font-bold ${
                      strike.is_atm ? 'text-blue-300 bg-blue-900/40' : 'text-white'
                    }`} style={{backgroundColor: strike.is_atm ? '#2a4a7f' : '#333'}}>
                      {strike.strike.toFixed(0)}
                      {strike.is_atm && <span className="ml-2 text-xs text-blue-400">ATM</span>}
                    </td>
                    
                    {/* Put Side Data */}
                    <td className="px-3 py-2 text-right" style={{backgroundColor: strike.is_atm ? '#1e3a5f' : '#000'}}>
                      <span className={`text-xs px-2 py-1 rounded font-semibold ${getPositionColor(strike.put.position)}`}>
                        {strike.put.position}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-bold text-white" style={{backgroundColor: strike.is_atm ? '#1e3a5f' : '#000'}}>{strike.put.ltp.toFixed(2)}</td>
                    <td className="px-3 py-2 text-right text-gray-200" style={{backgroundColor: strike.is_atm ? '#1e3a5f' : '#000'}}>{strike.put.iv.toFixed(2)}</td>
                    <td className="px-3 py-2 text-right text-gray-200" style={{backgroundColor: strike.is_atm ? '#1e3a5f' : '#000'}}>{formatNumber(strike.put.volume)}</td>
                    <td className={`px-3 py-2 text-right font-semibold ${strike.put.chg_oi > 0 ? 'text-green-400' : strike.put.chg_oi < 0 ? 'text-red-400' : 'text-gray-400'}`} style={{backgroundColor: strike.is_atm ? '#1e3a5f' : '#000'}}>
                      {strike.put.chg_oi > 0 ? '+' : ''}{formatNumber(strike.put.chg_oi)}
                    </td>
                    <td className="px-3 py-2 text-right text-white font-semibold" style={{backgroundColor: strike.is_atm ? '#1e3a5f' : '#000'}}>{formatNumber(strike.put.oi)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          
          {/* Table Legend */}
          <div className="bg-gray-900 border-t border-gray-700 px-4 py-3" style={{backgroundColor: '#1a1a1a'}}>
            <div className="flex flex-wrap gap-4 text-xs text-gray-400">
              <div><span className="font-semibold">OI:</span> Open Interest</div>
              <div><span className="font-semibold">ΔOI:</span> Change in OI</div>
              <div><span className="font-semibold">Vol:</span> Volume</div>
              <div><span className="font-semibold">IV:</span> Implied Volatility</div>
              <div><span className="font-semibold">LTP:</span> Last Traded Price</div>
              <div><span className="font-semibold">Chg:</span> Change</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
