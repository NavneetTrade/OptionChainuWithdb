import React, { useState, useEffect } from 'react'
import axios from 'axios'
import { BarChart, Bar, LineChart, Line, ComposedChart, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface BucketData {
  oi: number
  chg_oi: number
  volume: number
  iv: number
  delta: number
  gamma: number
  theta: number
  vega: number
}

interface BucketSummary {
  symbol: string
  expiry: string
  atm_strike: number
  spot_price: number
  buckets: {
    ce_itm: BucketData
    ce_otm: BucketData
    pe_itm: BucketData
    pe_otm: BucketData
  }
  pcr: {
    itm_oi: number
    otm_oi: number
    overall_oi: number
    itm_chgoi: number
    otm_chgoi: number
    overall_chgoi: number
    itm_volume: number
    otm_volume: number
    overall_volume: number
  }
}

interface GammaBlastData {
  symbol: string
  timestamp: string
  gamma_blast_probability: number
  predicted_direction: string
  confidence_level: string
  time_to_blast_minutes: number | null
  atm_iv: number
  iv_velocity: number
  iv_percentile: number
  atm_oi: number
  oi_velocity: number
  oi_acceleration: number
  gamma_concentration: number
  net_gex: number
  zero_gamma_level: number | null
  total_positive_gex: number
  total_negative_gex: number
}

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

interface SkewData {
  symbol: string
  expiry: string
  atm_iv: number
  spot_price: number
  metrics: {
    risk_reversal: number
    butterfly: number
  }
  skew_points: Array<{
    strike: number
    ce_iv: number
    pe_iv: number
    moneyness: number
  }>
}

interface SupportResistance {
  supports: Array<{
    level: number
    strength: string
    distance_pct: number
  }>
  resistances: Array<{
    level: number
    strength: string
    distance_pct: number
  }>
}

export default function EnhancedOptionChain() {
  const [symbol, setSymbol] = useState('NIFTY')
  const [expiry, setExpiry] = useState('')
  const [availableExpiries, setAvailableExpiries] = useState<string[]>([])
  const [itmCount, setItmCount] = useState(5) // ITM strikes selector
  
  const [optionChainData, setOptionChainData] = useState<OptionChainData | null>(null)
  const [bucketSummary, setBucketSummary] = useState<BucketSummary | null>(null)
  const [gammaBlastData, setGammaBlastData] = useState<GammaBlastData | null>(null)
  const [skewData, setSkewData] = useState<SkewData | null>(null)
  const [supportResistance, setSupportResistance] = useState<SupportResistance | null>(null)
  const [parityData, setParityData] = useState<any>(null)
  
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedSections, setExpandedSections] = useState({
    volatilitySkew: false,
    supportResistance: false,
    putCallParity: false
  })

  const symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'MIDCPNIFTY', 'SENSEX']

  useEffect(() => {
    fetchExpiries()
  }, [symbol])

  useEffect(() => {
    if (expiry) {
      fetchAllData()
    }
  }, [symbol, expiry])

  const fetchExpiries = async () => {
    try {
      const response = await axios.get(`${API_URL}/api/expiries/${symbol}`)
      const expiries = response.data.option_chain_expiries || []
      setAvailableExpiries(expiries)
      
      if (expiries.length > 0) {
        setExpiry(expiries[0])
      } else {
        setExpiry('')
        setError(`No expiry data found for ${symbol}`)
      }
    } catch (err: any) {
      console.error('Error fetching expiries:', err)
      setError('Failed to fetch available expiries')
    }
  }

  const fetchAllData = async () => {
    setLoading(true)
    setError(null)
    
    try {
      // Fetch all data in parallel
      const [chainRes, bucketRes, skewRes, srRes, parityRes] = await Promise.all([
        axios.get(`${API_URL}/api/option-chain/${symbol}?expiry=${expiry}`),
        axios.get(`${API_URL}/api/bucket-summary/${symbol}?expiry=${expiry}`),
        axios.get(`${API_URL}/api/volatility-skew/${symbol}?expiry=${expiry}`),
        axios.get(`${API_URL}/api/support-resistance/${symbol}?expiry=${expiry}`),
        axios.get(`${API_URL}/api/put-call-parity/${symbol}?expiry=${expiry}`)
      ])
      
      setOptionChainData(chainRes.data)
      setBucketSummary(bucketRes.data)
      setSkewData(skewRes.data)
      setSupportResistance(srRes.data)
      setParityData(parityRes.data)
      
      // Fetch gamma blast data separately (might not be available for all symbols)
      try {
        const gammaRes = await axios.get(`${API_URL}/api/gamma/${symbol}`)
        setGammaBlastData(gammaRes.data)
      } catch (gammaErr) {
        console.log('Gamma blast data not available for', symbol)
        setGammaBlastData(null)
      }
    } catch (err: any) {
      console.error('Error fetching data:', err)
      setError(err.response?.data?.detail || 'Failed to fetch option chain data')
    } finally {
      setLoading(false)
    }
  }

  const formatNumber = (num: number): string => {
    if (num >= 10000000) return `${(num / 10000000).toFixed(2)}Cr`
    if (num >= 100000) return `${(num / 100000).toFixed(2)}L`
    if (num >= 1000) return `${(num / 1000).toFixed(2)}K`
    return num.toFixed(0)
  }

  const formatDate = (dateStr: string): string => {
    const date = new Date(dateStr)
    return date.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' })
  }

  const getPositionColor = (position: string): string => {
    const colorMap: { [key: string]: string } = {
      'Long Build': '#10b981',
      'Short Covering': '#3b82f6',
      'Short Buildup': '#ef4444',
      'Long Unwinding': '#f59e0b',
      'Fresh Positions': '#8b5cf6',
      'Position Unwinding': '#6b7280'
    }
    return colorMap[position] || '#6b7280'
  }

  const getPCRColor = (pcr: number): string => {
    if (pcr > 1.2) return '#ef4444' // Bearish
    if (pcr < 0.8) return '#10b981' // Bullish
    return '#f59e0b' // Neutral
  }

  const getPCRSignal = (pcr: number): string => {
    if (pcr > 1.2) return 'Bearish'
    if (pcr < 0.8) return 'Bullish'
    return 'Neutral'
  }

  // Filter strikes based on ITM count
  const filteredStrikes = optionChainData ? (() => {
    const atmStrike = optionChainData.strikes.find(s => s.is_atm)?.strike || optionChainData.spot_price
    const atmIndex = optionChainData.strikes.findIndex(s => Math.abs(s.strike - atmStrike) < 50)
    
    if (atmIndex === -1) return optionChainData.strikes
    
    const startIndex = Math.max(0, atmIndex - itmCount)
    const endIndex = Math.min(optionChainData.strikes.length - 1, atmIndex + itmCount)
    
    return optionChainData.strikes.slice(startIndex, endIndex + 1)
  })() : []

  // Prepare combined OI, ChgOI & Volume data using FILTERED strikes
  const combinedChartData = filteredStrikes.map(s => ({
    strike: s.strike,
    'CE OI': s.call.oi,
    'PE OI': s.put.oi,
    'CE ChgOI': s.call.chg_oi,
    'PE ChgOI': s.put.chg_oi,
    'CE Volume': s.call.volume,
    'PE Volume': s.put.volume
  }))

  // Calculate bucket summary based on FILTERED strikes
  const filteredBucketSummary = filteredStrikes.length > 0 && optionChainData ? (() => {
    const spotPrice = optionChainData.spot_price
    
    // Separate ITM and OTM for calls and puts based on filtered strikes
    const ceItm = filteredStrikes.filter(s => s.strike < spotPrice)
    const ceOtm = filteredStrikes.filter(s => s.strike >= spotPrice)
    const peItm = filteredStrikes.filter(s => s.strike > spotPrice)
    const peOtm = filteredStrikes.filter(s => s.strike <= spotPrice)
    
    const sumBucket = (strikes: typeof filteredStrikes) => ({
      oi: strikes.reduce((sum, s) => sum + (s.call?.oi || s.put?.oi || 0), 0),
      chg_oi: strikes.reduce((sum, s) => sum + (s.call?.chg_oi || s.put?.chg_oi || 0), 0),
      volume: strikes.reduce((sum, s) => sum + (s.call?.volume || s.put?.volume || 0), 0),
      iv: strikes.length > 0 ? strikes.reduce((sum, s) => sum + (s.call?.iv || s.put?.iv || 0), 0) / strikes.length : 0,
      delta: strikes.reduce((sum, s) => sum + (s.call?.delta || s.put?.delta || 0), 0),
      gamma: strikes.reduce((sum, s) => sum + (s.call?.gamma || s.put?.gamma || 0), 0),
      theta: strikes.reduce((sum, s) => sum + (s.call?.theta || s.put?.theta || 0), 0),
      vega: strikes.reduce((sum, s) => sum + (s.call?.vega || s.put?.vega || 0), 0)
    })
    
    const ce_itm_data = sumBucket(ceItm.map(s => ({...s, call: s.call, put: {oi:0, chg_oi:0, volume:0, iv:0, delta:0, gamma:0, theta:0, vega:0} as any})))
    const ce_otm_data = sumBucket(ceOtm.map(s => ({...s, call: s.call, put: {oi:0, chg_oi:0, volume:0, iv:0, delta:0, gamma:0, theta:0, vega:0} as any})))
    const pe_itm_data = sumBucket(peItm.map(s => ({...s, put: s.put, call: {oi:0, chg_oi:0, volume:0, iv:0, delta:0, gamma:0, theta:0, vega:0} as any})))
    const pe_otm_data = sumBucket(peOtm.map(s => ({...s, put: s.put, call: {oi:0, chg_oi:0, volume:0, iv:0, delta:0, gamma:0, theta:0, vega:0} as any})))
    
    return {
      buckets: {
        ce_itm: ce_itm_data,
        ce_otm: ce_otm_data,
        pe_itm: pe_itm_data,
        pe_otm: pe_otm_data
      },
      pcr: {
        itm_oi: pe_itm_data.oi / (ce_itm_data.oi || 1),
        otm_oi: pe_otm_data.oi / (ce_otm_data.oi || 1),
        overall_oi: (pe_itm_data.oi + pe_otm_data.oi) / ((ce_itm_data.oi + ce_otm_data.oi) || 1),
        itm_chgoi: pe_itm_data.chg_oi / (ce_itm_data.chg_oi || 1),
        otm_chgoi: pe_otm_data.chg_oi / (ce_otm_data.chg_oi || 1),
        overall_chgoi: (pe_itm_data.chg_oi + pe_otm_data.chg_oi) / ((ce_itm_data.chg_oi + ce_otm_data.chg_oi) || 1),
        itm_volume: pe_itm_data.volume / (ce_itm_data.volume || 1),
        otm_volume: pe_otm_data.volume / (ce_otm_data.volume || 1),
        overall_volume: (pe_itm_data.volume + pe_otm_data.volume) / ((ce_itm_data.volume + ce_otm_data.volume) || 1)
      }
    }
  })() : null

  // Calculate Gamma Exposure
  const gammaExposureData = filteredStrikes.map(s => ({
    strike: s.strike,
    'Call Gamma Exposure': s.call.gamma * s.call.oi * (optionChainData?.spot_price || 0) * 0.01,
    'Put Gamma Exposure': s.put.gamma * s.put.oi * (optionChainData?.spot_price || 0) * 0.01 * -1,
    'Net Gamma': (s.call.gamma * s.call.oi - s.put.gamma * s.put.oi) * (optionChainData?.spot_price || 0) * 0.01
  }))

  // Calculate Gamma Summary Metrics
  const gammaSummary = gammaExposureData.length > 0 ? (() => {
    const totalCallGamma = gammaExposureData.reduce((sum, d) => sum + d['Call Gamma Exposure'], 0)
    const totalPutGamma = gammaExposureData.reduce((sum, d) => sum + Math.abs(d['Put Gamma Exposure']), 0)
    const netGamma = gammaExposureData.reduce((sum, d) => sum + d['Net Gamma'], 0)
    
    // Find Zero Gamma Level (strike where net gamma crosses zero)
    let zeroGammaStrike = 0
    for (let i = 0; i < gammaExposureData.length - 1; i++) {
      const curr = gammaExposureData[i]['Net Gamma']
      const next = gammaExposureData[i + 1]['Net Gamma']
      if ((curr >= 0 && next < 0) || (curr < 0 && next >= 0)) {
        // Linear interpolation to find exact zero crossing
        const ratio = Math.abs(curr) / (Math.abs(curr) + Math.abs(next))
        zeroGammaStrike = gammaExposureData[i].strike + ratio * (gammaExposureData[i + 1].strike - gammaExposureData[i].strike)
        break
      }
    }
    
    // Max Pain: Strike with maximum total OI
    const maxPainStrike = filteredStrikes.reduce((max, strike) => {
      const totalOI = strike.call.oi + strike.put.oi
      return totalOI > (filteredStrikes.find(s => s.strike === max)?.call.oi || 0) + (filteredStrikes.find(s => s.strike === max)?.put.oi || 0)
        ? strike.strike
        : max
    }, filteredStrikes[0]?.strike || 0)
    
    return {
      totalCallGamma,
      totalPutGamma,
      netGamma,
      zeroGammaStrike,
      maxPainStrike,
      gammaFlip: netGamma > 0 ? 'Positive (Resistance Above)' : 'Negative (Squeeze Potential)'
    }
  })() : null

  // Calculate Put-Call Parity for filtered strikes only
  const filteredParityData = parityData && filteredStrikes.length > 0 ? (() => {
    const spotPrice = optionChainData?.spot_price || 0
    const filteredStrikeValues = new Set(filteredStrikes.map(s => s.strike))
    
    // Filter parity pairs to only include strikes in our filtered list
    const filteredPairs = parityData.parity_pairs?.filter((pair: any) => 
      filteredStrikeValues.has(pair.call_strike) && filteredStrikeValues.has(pair.put_strike)
    ) || []
    
    return {
      ...parityData,
      parity_pairs: filteredPairs
    }
  })() : parityData

  // Filter volatility skew data based on filtered strikes
  const filteredSkewData = skewData && filteredStrikes.length > 0 ? (() => {
    const filteredStrikeValues = new Set(filteredStrikes.map(s => s.strike))
    
    const filteredSkewPoints = skewData.skew_points?.filter((point: any) => 
      filteredStrikeValues.has(point.strike)
    ) || []
    
    return {
      ...skewData,
      skew_points: filteredSkewPoints
    }
  })() : skewData

  if (loading && !optionChainData) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-lg">Loading option chain data...</div>
      </div>
    )
  }

  if (error && !optionChainData) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-800">{error}</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header Controls */}
      <div className="bg-black rounded-lg shadow p-4">
        <div className="grid grid-cols-4 gap-4 items-end">
          <div>
            <label className="block text-sm font-medium text-gray-200 mb-1">Symbol</label>
            <select 
              value={symbol} 
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full px-3 py-2 border border-gray-700 rounded-md bg-gray-800 text-white"
            >
              {symbols.map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-200 mb-1">Expiry</label>
            <select 
              value={expiry} 
              onChange={(e) => setExpiry(e.target.value)}
              className="w-full px-3 py-2 border border-gray-700 rounded-md bg-gray-800 text-white"
              disabled={!availableExpiries.length}
            >
              {availableExpiries.map(exp => (
                <option key={exp} value={exp}>{formatDate(exp)}</option>
              ))}
            </select>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-200 mb-1">ITM Strikes</label>
            <select 
              value={itmCount} 
              onChange={(e) => setItmCount(Number(e.target.value))}
              className="w-full px-3 py-2 border border-gray-700 rounded-md bg-gray-800 text-white"
            >
              <option value={1}>1</option>
              <option value={2}>2</option>
              <option value={3}>3</option>
              <option value={5}>5</option>
            </select>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-200 mb-1">Expiry</label>
            <select 
              value={expiry} 
              onChange={(e) => setExpiry(e.target.value)}
              className="w-full px-3 py-2 border border-gray-700 rounded-md bg-gray-800 text-white"
              disabled={!availableExpiries.length}
            >
              {availableExpiries.map(exp => (
                <option key={exp} value={exp}>{formatDate(exp)}</option>
              ))}
            </select>
          </div>
          
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-200 mb-1">&nbsp;</label>
            <button 
              onClick={fetchAllData}
              disabled={!expiry || loading}
              className="w-full bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:bg-gray-400"
            >
              {loading ? 'Loading...' : 'Refresh'}
            </button>
          </div>
        </div>
      </div>

      {optionChainData && (
        <>
          {/* Spot Price Banner */}
          <div className="bg-gradient-to-r from-blue-600 to-blue-700 rounded-lg p-4 text-white text-center">
            <div className="text-2xl font-bold">{symbol} Spot: ₹{optionChainData.spot_price.toFixed(2)}</div>
            <div className="text-sm opacity-90">Expiry: {formatDate(expiry)} | Last Update: {new Date(optionChainData.timestamp).toLocaleTimeString()}</div>
          </div>

          {/* OI, ChgOI & Volume Distribution - Combined Chart (matching Streamlit) */}
          <div className="bg-black rounded-lg shadow p-6">
            <h3 className="text-lg font-semibold mb-4">OI, ChgOI & Volume Distribution (ITM {itmCount} strikes)</h3>
            <ResponsiveContainer width="100%" height={400}>
              <ComposedChart data={combinedChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#444" />
                <XAxis dataKey="strike" angle={-45} textAnchor="end" height={80} stroke="#999" />
                <YAxis yAxisId="left" tickFormatter={(value) => formatNumber(value)} stroke="#999" />
                <YAxis yAxisId="right" orientation="right" tickFormatter={(value) => formatNumber(value)} stroke="#999" />
                <Tooltip formatter={(value: number) => formatNumber(value)} contentStyle={{backgroundColor: '#1a1a1a', border: '1px solid #444'}} />
                <Legend />
                <Bar yAxisId="left" dataKey="CE OI" fill="#1f77b4" opacity={0.7} />
                <Bar yAxisId="left" dataKey="PE OI" fill="#2ca02c" opacity={0.7} />
                <Bar yAxisId="left" dataKey="CE ChgOI" fill="#aec7e8" opacity={0.7} />
                <Bar yAxisId="left" dataKey="PE ChgOI" fill="#98df8a" opacity={0.7} />
                <Line yAxisId="right" type="monotone" dataKey="CE Volume" stroke="#ff7f0e" strokeWidth={2} dot={{ r: 4 }} />
                <Line yAxisId="right" type="monotone" dataKey="PE Volume" stroke="#d62728" strokeWidth={2} dot={{ r: 4 }} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* Bucket Summary */}
          {filteredBucketSummary && (
            <div className="bg-black rounded-lg shadow p-6">
              <h3 className="text-lg font-semibold mb-4">Bucket Summary with Greeks Analysis (ITM {itmCount} strikes)</h3>
              
              <div className="grid grid-cols-3 gap-6">
                {/* Calls (CE) */}
                <div>
                  <h4 className="font-semibold text-lg mb-3">Calls (CE)</h4>
                  
                  <div className="mb-4">
                    <p className="text-sm font-medium text-gray-600 mb-2">ITM (below spot)</p>
                    <div className="bg-gradient-to-r from-green-50 to-transparent border-l-4 border-green-500 p-3 rounded">
                      <div className="text-green-700 font-bold">OI: {formatNumber(filteredBucketSummary.buckets.ce_itm.oi)}</div>
                      <div className="text-green-600 font-bold">ChgOI: {filteredBucketSummary.buckets.ce_itm.chg_oi >= 0 ? '+' : ''}{formatNumber(filteredBucketSummary.buckets.ce_itm.chg_oi)}</div>
                      <div className="text-sm">Volume: {formatNumber(filteredBucketSummary.buckets.ce_itm.volume)}</div>
                      <div className="text-sm">IV: {filteredBucketSummary.buckets.ce_itm.iv.toFixed(2)}%</div>
                      <div className="text-sm">Delta: {filteredBucketSummary.buckets.ce_itm.delta.toFixed(4)}</div>
                      <div className="text-xs text-gray-600">
                        Gamma: {filteredBucketSummary.buckets.ce_itm.gamma.toFixed(4)} | Theta: {filteredBucketSummary.buckets.ce_itm.theta.toFixed(2)} | Vega: {filteredBucketSummary.buckets.ce_itm.vega.toFixed(2)}
                      </div>
                    </div>
                  </div>
                  
                  <div>
                    <p className="text-sm font-medium text-gray-600 mb-2">OTM (above spot)</p>
                    <div className="bg-gradient-to-r from-blue-50 to-transparent border-l-4 border-blue-500 p-3 rounded">
                      <div className="text-blue-700 font-bold">OI: {formatNumber(filteredBucketSummary.buckets.ce_otm.oi)}</div>
                      <div className="text-blue-600 font-bold">ChgOI: {filteredBucketSummary.buckets.ce_otm.chg_oi >= 0 ? '+' : ''}{formatNumber(filteredBucketSummary.buckets.ce_otm.chg_oi)}</div>
                      <div className="text-sm">Volume: {formatNumber(filteredBucketSummary.buckets.ce_otm.volume)}</div>
                      <div className="text-sm">IV: {filteredBucketSummary.buckets.ce_otm.iv.toFixed(2)}%</div>
                      <div className="text-sm">Delta: {filteredBucketSummary.buckets.ce_otm.delta.toFixed(4)}</div>
                      <div className="text-xs text-gray-600">
                        Gamma: {filteredBucketSummary.buckets.ce_otm.gamma.toFixed(4)} | Theta: {filteredBucketSummary.buckets.ce_otm.theta.toFixed(2)} | Vega: {filteredBucketSummary.buckets.ce_otm.vega.toFixed(2)}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Puts (PE) */}
                <div>
                  <h4 className="font-semibold text-lg mb-3">Puts (PE)</h4>
                  
                  <div className="mb-4">
                    <p className="text-sm font-medium text-gray-600 mb-2">ITM (above spot)</p>
                    <div className="bg-gradient-to-r from-red-50 to-transparent border-l-4 border-red-500 p-3 rounded">
                      <div className="text-red-700 font-bold">OI: {formatNumber(filteredBucketSummary.buckets.pe_itm.oi)}</div>
                      <div className="text-red-600 font-bold">ChgOI: {filteredBucketSummary.buckets.pe_itm.chg_oi >= 0 ? '+' : ''}{formatNumber(filteredBucketSummary.buckets.pe_itm.chg_oi)}</div>
                      <div className="text-sm">Volume: {formatNumber(filteredBucketSummary.buckets.pe_itm.volume)}</div>
                      <div className="text-sm">IV: {filteredBucketSummary.buckets.pe_itm.iv.toFixed(2)}%</div>
                      <div className="text-sm">Delta: {filteredBucketSummary.buckets.pe_itm.delta.toFixed(4)}</div>
                      <div className="text-xs text-gray-600">
                        Gamma: {filteredBucketSummary.buckets.pe_itm.gamma.toFixed(4)} | Theta: {filteredBucketSummary.buckets.pe_itm.theta.toFixed(2)} | Vega: {filteredBucketSummary.buckets.pe_itm.vega.toFixed(2)}
                      </div>
                    </div>
                  </div>
                  
                  <div>
                    <p className="text-sm font-medium text-gray-600 mb-2">OTM (below spot)</p>
                    <div className="bg-gradient-to-r from-orange-50 to-transparent border-l-4 border-orange-500 p-3 rounded">
                      <div className="text-orange-700 font-bold">OI: {formatNumber(filteredBucketSummary.buckets.pe_otm.oi)}</div>
                      <div className="text-orange-600 font-bold">ChgOI: {filteredBucketSummary.buckets.pe_otm.chg_oi >= 0 ? '+' : ''}{formatNumber(filteredBucketSummary.buckets.pe_otm.chg_oi)}</div>
                      <div className="text-sm">Volume: {formatNumber(filteredBucketSummary.buckets.pe_otm.volume)}</div>
                      <div className="text-sm">IV: {filteredBucketSummary.buckets.pe_otm.iv.toFixed(2)}%</div>
                      <div className="text-sm">Delta: {filteredBucketSummary.buckets.pe_otm.delta.toFixed(4)}</div>
                      <div className="text-xs text-gray-600">
                        Gamma: {filteredBucketSummary.buckets.pe_otm.gamma.toFixed(4)} | Theta: {filteredBucketSummary.buckets.pe_otm.theta.toFixed(2)} | Vega: {filteredBucketSummary.buckets.pe_otm.vega.toFixed(2)}
                      </div>
                    </div>
                  </div>
                </div>

                {/* PCR Analysis */}
                <div>
                  <h4 className="font-semibold text-lg mb-3">PCR Analysis</h4>
                  
                  <div className="space-y-2">
                    <div>
                      <p className="text-sm font-medium text-gray-600 mb-1">Open Interest PCR</p>
                      <div 
                        className="p-2 rounded border-l-3" 
                        style={{
                          backgroundColor: `${getPCRColor(filteredBucketSummary.pcr.overall_oi)}15`,
                          borderLeftColor: getPCRColor(filteredBucketSummary.pcr.overall_oi),
                          borderLeftWidth: '3px'
                        }}
                      >
                        <div className="font-bold" style={{ color: getPCRColor(filteredBucketSummary.pcr.overall_oi) }}>
                          Overall: {filteredBucketSummary.pcr.overall_oi.toFixed(3)} ({getPCRSignal(filteredBucketSummary.pcr.overall_oi)})
                        </div>
                        <div className="flex gap-2 text-sm mt-1">
                          <span>ITM: {filteredBucketSummary.pcr.itm_oi.toFixed(3)}</span>
                          <span>OTM: {filteredBucketSummary.pcr.otm_oi.toFixed(3)}</span>
                        </div>
                      </div>
                    </div>
                    
                    <div>
                      <p className="text-sm font-medium text-gray-600 mb-1">Change in OI PCR</p>
                      <div className="bg-gray-900 border-l-3 border-gray-400 p-2 rounded">
                        <div className="font-bold">Overall: {filteredBucketSummary.pcr.overall_chgoi.toFixed(3)}</div>
                        <div className="flex gap-2 text-sm mt-1">
                          <span>ITM: {filteredBucketSummary.pcr.itm_chgoi.toFixed(3)}</span>
                          <span>OTM: {filteredBucketSummary.pcr.otm_chgoi.toFixed(3)}</span>
                        </div>
                      </div>
                    </div>
                    
                    <div>
                      <p className="text-sm font-medium text-gray-600 mb-1">Volume PCR</p>
                      <div className="bg-gray-900 border-l-3 border-gray-400 p-2 rounded">
                        <div className="font-bold">Overall: {filteredBucketSummary.pcr.overall_volume.toFixed(3)}</div>
                        <div className="flex gap-2 text-sm mt-1">
                          <span>ITM: {filteredBucketSummary.pcr.itm_volume.toFixed(3)}</span>
                          <span>OTM: {filteredBucketSummary.pcr.otm_volume.toFixed(3)}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Option Chain Table */}
          <div className="bg-black rounded-lg shadow overflow-hidden">
            <div className="p-4 bg-gray-900 border-b">
              <h3 className="text-lg font-semibold">Option Chain</h3>
            </div>
            
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-700">
                <thead className="bg-gray-900">
                  <tr>
                    <th colSpan={6} className="px-2 py-2 text-center text-xs font-medium text-gray-300 uppercase bg-green-50">Calls (CE)</th>
                    <th className="px-2 py-2 text-xs font-medium text-gray-300 uppercase">Strike</th>
                    <th colSpan={6} className="px-2 py-2 text-center text-xs font-medium text-gray-300 uppercase bg-red-50">Puts (PE)</th>
                  </tr>
                  <tr>
                    {/* CE Headers */}
                    <th className="px-2 py-2 text-xs font-medium text-gray-300 uppercase">OI</th>
                    <th className="px-2 py-2 text-xs font-medium text-gray-300 uppercase">ChgOI</th>
                    <th className="px-2 py-2 text-xs font-medium text-gray-300 uppercase">Volume</th>
                    <th className="px-2 py-2 text-xs font-medium text-gray-300 uppercase">IV</th>
                    <th className="px-2 py-2 text-xs font-medium text-gray-300 uppercase">LTP</th>
                    <th className="px-2 py-2 text-xs font-medium text-gray-300 uppercase">Position</th>
                    {/* Strike */}
                    <th className="px-2 py-2 text-xs font-medium text-gray-300 uppercase bg-yellow-50">Strike</th>
                    {/* PE Headers */}
                    <th className="px-2 py-2 text-xs font-medium text-gray-300 uppercase">Position</th>
                    <th className="px-2 py-2 text-xs font-medium text-gray-300 uppercase">LTP</th>
                    <th className="px-2 py-2 text-xs font-medium text-gray-300 uppercase">IV</th>
                    <th className="px-2 py-2 text-xs font-medium text-gray-300 uppercase">Volume</th>
                    <th className="px-2 py-2 text-xs font-medium text-gray-300 uppercase">ChgOI</th>
                    <th className="px-2 py-2 text-xs font-medium text-gray-300 uppercase">OI</th>
                  </tr>
                </thead>
                <tbody className="bg-black divide-y divide-gray-700">
                  {filteredStrikes.map((strike, idx) => (
                    <tr 
                      key={idx}
                      className={strike.is_atm ? 'bg-yellow-50 font-semibold' : ''}
                    >
                      {/* CE Data */}
                      <td className="px-2 py-2 text-sm text-right">{formatNumber(strike.call.oi)}</td>
                      <td className={`px-2 py-2 text-sm text-right ${strike.call.chg_oi > 0 ? 'text-green-600' : strike.call.chg_oi < 0 ? 'text-red-600' : ''}`}>
                        {strike.call.chg_oi > 0 ? '+' : ''}{formatNumber(strike.call.chg_oi)}
                      </td>
                      <td className="px-2 py-2 text-sm text-right">{formatNumber(strike.call.volume)}</td>
                      <td className="px-2 py-2 text-sm text-right">{strike.call.iv.toFixed(2)}%</td>
                      <td className={`px-2 py-2 text-sm text-right font-medium ${strike.call.change > 0 ? 'text-green-600' : strike.call.change < 0 ? 'text-red-600' : ''}`}>
                        ₹{strike.call.ltp.toFixed(2)}
                      </td>
                      <td className="px-2 py-2 text-xs text-center">
                        <span 
                          className="px-2 py-1 rounded text-white"
                          style={{ backgroundColor: getPositionColor(strike.call.position) }}
                        >
                          {strike.call.position}
                        </span>
                      </td>
                      
                      {/* Strike */}
                      <td className="px-2 py-2 text-sm font-bold text-center bg-yellow-50">
                        {strike.strike.toFixed(0)}
                      </td>
                      
                      {/* PE Data */}
                      <td className="px-2 py-2 text-xs text-center">
                        <span 
                          className="px-2 py-1 rounded text-white"
                          style={{ backgroundColor: getPositionColor(strike.put.position) }}
                        >
                          {strike.put.position}
                        </span>
                      </td>
                      <td className={`px-2 py-2 text-sm text-right font-medium ${strike.put.change > 0 ? 'text-green-600' : strike.put.change < 0 ? 'text-red-600' : ''}`}>
                        ₹{strike.put.ltp.toFixed(2)}
                      </td>
                      <td className="px-2 py-2 text-sm text-right">{strike.put.iv.toFixed(2)}%</td>
                      <td className="px-2 py-2 text-sm text-right">{formatNumber(strike.put.volume)}</td>
                      <td className={`px-2 py-2 text-sm text-right ${strike.put.chg_oi > 0 ? 'text-green-600' : strike.put.chg_oi < 0 ? 'text-red-600' : ''}`}>
                        {strike.put.chg_oi > 0 ? '+' : ''}{formatNumber(strike.put.chg_oi)}
                      </td>
                      <td className="px-2 py-2 text-sm text-right">{formatNumber(strike.put.oi)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Put-Call Parity Analysis - Expandable */}
          {filteredParityData && filteredParityData.parity_pairs && filteredParityData.parity_pairs.length > 0 && (
            <div className="bg-black rounded-lg shadow">
              <button
                onClick={() => setExpandedSections(prev => ({ ...prev, putCallParity: !prev.putCallParity }))}
                className="w-full px-6 py-4 flex justify-between items-center text-left hover:bg-gray-900"
              >
                <h3 className="text-lg font-semibold">Put-Call Parity Analysis (ITM {itmCount} strikes)</h3>
                <span className="text-2xl">{expandedSections.putCallParity ? '−' : '+'}</span>
              </button>
              
              {expandedSections.putCallParity && (
                <div className="px-6 py-4 border-t overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-700">
                    <thead className="bg-gray-900">
                      <tr>
                        <th className="px-4 py-2 text-xs font-medium text-gray-300 uppercase">Distance</th>
                        <th className="px-4 py-2 text-xs font-medium text-gray-300 uppercase">Call Strike</th>
                        <th className="px-4 py-2 text-xs font-medium text-gray-300 uppercase">Put Strike</th>
                        <th className="px-4 py-2 text-xs font-medium text-gray-300 uppercase">Call Price</th>
                        <th className="px-4 py-2 text-xs font-medium text-gray-300 uppercase">Put Price</th>
                        <th className="px-4 py-2 text-xs font-medium text-gray-300 uppercase">Call IV</th>
                        <th className="px-4 py-2 text-xs font-medium text-gray-300 uppercase">Put IV</th>
                        <th className="px-4 py-2 text-xs font-medium text-gray-300 uppercase">Deviation</th>
                        <th className="px-4 py-2 text-xs font-medium text-gray-300 uppercase">Mispricing</th>
                      </tr>
                    </thead>
                    <tbody className="bg-black divide-y divide-gray-700">
                      {filteredParityData.parity_pairs.map((pair: any, idx: number) => (
                        <tr key={idx}>
                          <td className="px-4 py-2 text-sm text-center">{pair.distance}</td>
                          <td className="px-4 py-2 text-sm text-center">{pair.call_strike}</td>
                          <td className="px-4 py-2 text-sm text-center">{pair.put_strike}</td>
                          <td className="px-4 py-2 text-sm text-right">₹{pair.call_price.toFixed(2)}</td>
                          <td className="px-4 py-2 text-sm text-right">₹{pair.put_price.toFixed(2)}</td>
                          <td className="px-4 py-2 text-sm text-right">{pair.call_iv.toFixed(1)}%</td>
                          <td className="px-4 py-2 text-sm text-right">{pair.put_iv.toFixed(1)}%</td>
                          <td className="px-4 py-2 text-sm text-right">{pair.deviation_pct.toFixed(2)}%</td>
                          <td className="px-4 py-2 text-sm text-center">
                            <span 
                              className={`px-3 py-1 rounded text-white ${
                                pair.mispricing === 'Overvalued' ? 'bg-red-500' :
                                pair.mispricing === 'Undervalued' ? 'bg-green-500' :
                                'bg-yellow-500'
                              }`}
                            >
                              {pair.mispricing}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Gamma Exposure Analysis */}
          <div className="bg-black rounded-lg shadow p-6">
            <h3 className="text-lg font-semibold mb-4">Gamma Exposure Analysis (ITM {itmCount} strikes)</h3>
            
            {/* Gamma Blast Probability Forecast */}
            {gammaBlastData && (
              <div className="bg-gradient-to-r from-red-900/20 to-orange-900/20 border-2 border-red-500/50 rounded-lg p-6 mb-6">
                <h4 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                  <span className="text-2xl">🎯</span>
                  Gamma Blast Probability Forecast [REAL-TIME]
                </h4>
                
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                  <div className="bg-gray-900/70 p-3 rounded-lg border border-gray-700">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xl">🟢</span>
                      <div className="text-xs text-gray-400">Blast Probability</div>
                    </div>
                    <div className="text-2xl font-bold text-green-400">
                      {(gammaBlastData.gamma_blast_probability * 100).toFixed(1)}%
                    </div>
                  </div>
                  
                  <div className="bg-gray-900/70 p-3 rounded-lg border border-gray-700">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xl">⏳</span>
                      <div className="text-xs text-gray-400">Confidence Level</div>
                    </div>
                    <div className="text-xl font-bold text-yellow-400">
                      {gammaBlastData.confidence_level || 'MEDIUM'}
                    </div>
                  </div>
                  
                  <div className="bg-gray-900/70 p-3 rounded-lg border border-gray-700">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xl">{gammaBlastData.predicted_direction === 'UPSIDE' ? '📈' : '📉'}</span>
                      <div className="text-xs text-gray-400">Predicted Direction</div>
                    </div>
                    <div className={`text-xl font-bold ${gammaBlastData.predicted_direction === 'UPSIDE' ? 'text-green-400' : 'text-red-400'}`}>
                      {gammaBlastData.predicted_direction || 'NEUTRAL'}
                    </div>
                  </div>
                  
                  <div className="bg-gray-900/70 p-3 rounded-lg border border-gray-700">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xl">⏱️</span>
                      <div className="text-xs text-gray-400">Time to Blast</div>
                    </div>
                    <div className="text-2xl font-bold text-orange-400">
                      {gammaBlastData.time_to_blast_minutes ? `${gammaBlastData.time_to_blast_minutes}m` : 'N/A'}
                    </div>
                  </div>
                </div>
                
                {/* Detailed Indicator Breakdown */}
                <div className="bg-gray-900/50 p-4 rounded-lg border border-gray-700">
                  <h5 className="text-md font-semibold text-white mb-3 flex items-center gap-2">
                    <span className="text-lg">📊</span>
                    Detailed Indicator Breakdown
                  </h5>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    {/* IV Momentum */}
                    <div>
                      <h6 className="text-sm font-bold text-blue-400 mb-2">IV Momentum</h6>
                      <div className="space-y-1 text-xs">
                        <div className="flex justify-between">
                          <span className="text-gray-400">IV Velocity:</span>
                          <span className="text-white font-mono">{gammaBlastData.iv_velocity.toFixed(4)}% per sec</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">IV Percentile:</span>
                          <span className="text-white font-mono">{gammaBlastData.iv_percentile.toFixed(2)}% (Range position)</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Implied Move:</span>
                          <span className="text-white font-mono">₹{((optionChainData?.spot_price || 0) * (gammaBlastData.atm_iv / 100)).toFixed(2)}</span>
                        </div>
                      </div>
                    </div>
                    
                    {/* OI Dynamics */}
                    <div>
                      <h6 className="text-sm font-bold text-purple-400 mb-2">OI Dynamics</h6>
                      <div className="space-y-1 text-xs">
                        <div className="flex justify-between">
                          <span className="text-gray-400">OI Acceleration:</span>
                          <span className="text-white font-mono">{gammaBlastData.oi_acceleration.toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">OI Velocity:</span>
                          <span className="text-white font-mono">{gammaBlastData.oi_velocity.toFixed(2)} per sec</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Unwinding Intensity:</span>
                          <span className="text-white font-mono">{(Math.abs(gammaBlastData.oi_acceleration) / Math.max(gammaBlastData.atm_oi, 1) * 100).toFixed(2)}%</span>
                        </div>
                      </div>
                    </div>
                    
                    {/* Gamma Metrics */}
                    <div>
                      <h6 className="text-sm font-bold text-green-400 mb-2">Gamma Metrics</h6>
                      <div className="space-y-1 text-xs">
                        <div className="flex justify-between">
                          <span className="text-gray-400">Gamma Concentration at ATM:</span>
                          <span className="text-white font-mono">{(gammaBlastData.gamma_concentration * 100).toFixed(2)}%</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Gamma Gradient:</span>
                          <span className="text-white font-mono">{((gammaBlastData.total_positive_gex - gammaBlastData.total_negative_gex) / 1e6).toFixed(2)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">ATM Gamma:</span>
                          <span className="text-white font-mono">{(gammaBlastData.net_gex / 1e6).toFixed(2)}</span>
                        </div>
                      </div>
                    </div>
                    
                    {/* Delta Analysis */}
                    <div>
                      <h6 className="text-sm font-bold text-yellow-400 mb-2">Delta Analysis</h6>
                      <div className="space-y-1 text-xs">
                        <div className="flex justify-between">
                          <span className="text-gray-400">Delta Imbalance:</span>
                          <span className="text-white font-mono">{((gammaBlastData.total_positive_gex - gammaBlastData.total_negative_gex) / (gammaBlastData.total_positive_gex + gammaBlastData.total_negative_gex) * 100).toFixed(4)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Delta Skew:</span>
                          <span className="text-white font-mono">{((gammaBlastData.atm_iv - 20) / 20 * 100).toFixed(4)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-400">Regime:</span>
                          <span className="text-white font-mono">NORMAL</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                
                <div className="mt-3 text-xs text-gray-400">
                  Last Updated: {new Date(gammaBlastData.timestamp).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' })}
                </div>
              </div>
            )}
            
            {/* Gamma Summary Metrics */}
            {gammaSummary && (
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
                <div className="bg-gray-900 p-4 rounded-lg border border-gray-800">
                  <div className="text-xs text-gray-400 mb-1">Total Call Gamma</div>
                  <div className="text-lg font-bold text-green-400">{(gammaSummary.totalCallGamma / 1e6).toFixed(2)}M</div>
                </div>
                <div className="bg-gray-900 p-4 rounded-lg border border-gray-800">
                  <div className="text-xs text-gray-400 mb-1">Total Put Gamma</div>
                  <div className="text-lg font-bold text-red-400">{(gammaSummary.totalPutGamma / 1e6).toFixed(2)}M</div>
                </div>
                <div className="bg-gray-900 p-4 rounded-lg border border-gray-800">
                  <div className="text-xs text-gray-400 mb-1">Net Gamma</div>
                  <div className={`text-lg font-bold ${gammaSummary.netGamma > 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {gammaSummary.netGamma > 0 ? '+' : ''}{(gammaSummary.netGamma / 1e6).toFixed(2)}M
                  </div>
                </div>
                <div className="bg-gray-900 p-4 rounded-lg border border-gray-800">
                  <div className="text-xs text-gray-400 mb-1">Zero Gamma Level</div>
                  <div className="text-lg font-bold text-blue-400">
                    {gammaSummary.zeroGammaStrike > 0 ? gammaSummary.zeroGammaStrike.toFixed(0) : 'N/A'}
                  </div>
                </div>
                <div className="bg-gray-900 p-4 rounded-lg border border-gray-800">
                  <div className="text-xs text-gray-400 mb-1">Max Pain Strike</div>
                  <div className="text-lg font-bold text-yellow-400">{gammaSummary.maxPainStrike.toFixed(0)}</div>
                </div>
                <div className="bg-gray-900 p-4 rounded-lg border border-gray-800">
                  <div className="text-xs text-gray-400 mb-1">Gamma Regime</div>
                  <div className={`text-sm font-bold ${gammaSummary.netGamma > 0 ? 'text-green-400' : 'text-orange-400'}`}>
                    {gammaSummary.gammaFlip}
                  </div>
                </div>
              </div>
            )}
            
            <ResponsiveContainer width="100%" height={400}>
              <ComposedChart data={gammaExposureData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#444" />
                <XAxis dataKey="strike" angle={-45} textAnchor="end" height={80} stroke="#999" />
                <YAxis tickFormatter={(value) => formatNumber(value)} stroke="#999" />
                <Tooltip formatter={(value: number) => formatNumber(value)} contentStyle={{backgroundColor: '#1a1a1a', border: '1px solid #444'}} />
                <Legend />
                <Bar dataKey="Call Gamma Exposure" fill="#22c55e" opacity={0.8} />
                <Bar dataKey="Put Gamma Exposure" fill="#ef4444" opacity={0.8} />
                <Line type="monotone" dataKey="Net Gamma" stroke="#3b82f6" strokeWidth={3} dot={{ r: 5 }} />
              </ComposedChart>
            </ResponsiveContainer>
            <div className="mt-4 text-sm text-gray-400 space-y-1">
              <p>• <span className="font-semibold text-green-400">Positive Net Gamma:</span> Market makers sell on rallies (resistance above), buy on dips (support below)</p>
              <p>• <span className="font-semibold text-red-400">Negative Net Gamma:</span> Market makers buy on rallies (potential squeeze), sell on dips (acceleration down)</p>
              <p>• <span className="font-semibold text-blue-400">Zero Gamma Level:</span> Strike where gamma neutrality occurs - critical pivot point for MM hedging behavior</p>
              <p>• <span className="font-semibold text-yellow-400">Max Pain:</span> Strike with highest total OI - where most options expire worthless</p>
            </div>
          </div>

          {/* Volatility Skew - Expandable */}
          {filteredSkewData && (
            <div className="bg-black rounded-lg shadow">
              <button
                onClick={() => setExpandedSections(prev => ({ ...prev, volatilitySkew: !prev.volatilitySkew }))}
                className="w-full px-6 py-4 flex justify-between items-center text-left hover:bg-gray-900"
              >
                <h3 className="text-lg font-semibold">Volatility Skew Analysis (ITM  strikes)</h3>
                <span className="text-2xl">{expandedSections.volatilitySkew ? '−' : '+'}</span>
              </button>
              
              {expandedSections.volatilitySkew && (
                <div className="px-6 py-4 border-t">
                  <div className="grid grid-cols-3 gap-4 mb-6">
                    <div className="text-center">
                      <div className="text-sm text-gray-600">ATM IV</div>
                      <div className="text-2xl font-bold">{filteredSkewData.atm_iv.toFixed(2)}%</div>
                    </div>
                    <div className="text-center">
                      <div className="text-sm text-gray-600">Risk Reversal</div>
                      <div className="text-2xl font-bold">{filteredSkewData.metrics.risk_reversal > 0 ? '+' : ''}{filteredSkewData.metrics.risk_reversal.toFixed(2)}%</div>
                      <div className="text-xs text-gray-300">
                        {filteredSkewData.metrics.risk_reversal > 2 ? 'Strong Put Skew' : 
                         filteredSkewData.metrics.risk_reversal < -2 ? 'Call Skew' : 'Balanced'}
                      </div>
                    </div>
                    <div className="text-center">
                      <div className="text-sm text-gray-600">Butterfly</div>
                      <div className="text-2xl font-bold">{filteredSkewData.metrics.butterfly > 0 ? '+' : ''}{filteredSkewData.metrics.butterfly.toFixed(2)}%</div>
                    </div>
                  </div>
                  
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={filteredSkewData.skew_points}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="strike" />
                      <YAxis />
                      <Tooltip />
                      <Legend />
                      <Line type="monotone" dataKey="ce_iv" stroke="#10b981" name="Call IV" strokeWidth={2} />
                      <Line type="monotone" dataKey="pe_iv" stroke="#ef4444" name="Put IV" strokeWidth={2} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          )}

          {/* Support & Resistance - Expandable */}
          {supportResistance && (
            <div className="bg-black rounded-lg shadow">
              <button
                onClick={() => setExpandedSections(prev => ({ ...prev, supportResistance: !prev.supportResistance }))}
                className="w-full px-6 py-4 flex justify-between items-center text-left hover:bg-gray-900"
              >
                <h3 className="text-lg font-semibold">Support & Resistance Levels</h3>
                <span className="text-2xl">{expandedSections.supportResistance ? '−' : '+'}</span>
              </button>
              
              {expandedSections.supportResistance && (
                <div className="px-6 py-4 border-t">
                  <div className="grid grid-cols-2 gap-6">
                    <div>
                      <h4 className="font-semibold mb-2 text-green-700">Key Support Levels</h4>
                      {supportResistance.supports.length > 0 ? (
                        <ul className="space-y-2">
                          {supportResistance.supports.map((level, idx) => (
                            <li key={idx} className="flex justify-between items-center bg-green-50 p-2 rounded">
                              <span className="font-medium">₹{level.level.toFixed(0)}</span>
                              <span className="text-sm">
                                <span className={level.strength === 'Strong' ? 'text-green-700 font-semibold' : 'text-green-600'}>
                                  {level.strength}
                                </span>
                                <span className="text-gray-300 ml-2">({level.distance_pct.toFixed(1)}% below)</span>
                              </span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-gray-300">No significant support levels found</p>
                      )}
                    </div>
                    
                    <div>
                      <h4 className="font-semibold mb-2 text-red-700">Key Resistance Levels</h4>
                      {supportResistance.resistances.length > 0 ? (
                        <ul className="space-y-2">
                          {supportResistance.resistances.map((level, idx) => (
                            <li key={idx} className="flex justify-between items-center bg-red-50 p-2 rounded">
                              <span className="font-medium">₹{level.level.toFixed(0)}</span>
                              <span className="text-sm">
                                <span className={level.strength === 'Strong' ? 'text-red-700 font-semibold' : 'text-red-600'}>
                                  {level.strength}
                                </span>
                                <span className="text-gray-300 ml-2">({level.distance_pct.toFixed(1)}% above)</span>
                              </span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="text-gray-300">No significant resistance levels found</p>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Position Legend */}
          <div className="bg-black rounded-lg shadow p-4">
            <h4 className="font-semibold mb-2">Position Type Legend</h4>
            <div className="flex flex-wrap gap-2">
              {[
                'Long Build', 'Short Covering', 'Short Buildup', 
                'Long Unwinding', 'Fresh Positions', 'Position Unwinding'
              ].map(pos => (
                <span 
                  key={pos}
                  className="px-3 py-1 rounded text-white text-sm"
                  style={{ backgroundColor: getPositionColor(pos) }}
                >
                  {pos}
                </span>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
