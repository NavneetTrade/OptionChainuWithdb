import { useEffect, useState } from 'react'
import axios from 'axios'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface SymbolDetailProps {
  symbol: string
  liveData?: any
}

export default function SymbolDetail({ symbol, liveData }: SymbolDetailProps) {
  const [currentData, setCurrentData] = useState<any>(null)
  const [historyData, setHistoryData] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (symbol) {
      fetchSymbolData()
    }
  }, [symbol])

  // Update with live data
  useEffect(() => {
    if (liveData) {
      setCurrentData(liveData)
    }
  }, [liveData])

  const fetchSymbolData = async () => {
    setLoading(true)
    try {
      const [currentResponse, historyResponse] = await Promise.all([
        axios.get(`${API_URL}/api/gamma/${symbol}`),
        axios.get(`${API_URL}/api/gamma/history/${symbol}?hours=6`)
      ])
      setCurrentData(currentResponse.data)
      setHistoryData(historyResponse.data.data)
    } catch (error) {
      console.error('Error fetching symbol data:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12 bg-dark-card rounded-lg">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gamma-blue"></div>
      </div>
    )
  }

  if (!currentData) {
    return (
      <div className="bg-dark-card rounded-lg p-8 text-center">
        <p className="text-gray-400">No data available for {symbol}</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Current Metrics Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard 
          title="Gamma Blast" 
          value={`${(currentData.gamma_blast_probability * 100).toFixed(1)}%`}
          subtitle={currentData.predicted_direction}
          color={currentData.gamma_blast_probability > 0.5 ? 'gamma-red' : 'gamma-green'}
        />
        <MetricCard 
          title="Net GEX" 
          value={`${(currentData.net_gex / 1_000_000).toFixed(2)}M`}
          subtitle="Gamma Exposure"
          color="gamma-blue"
        />
        <MetricCard 
          title="ATM IV" 
          value={`${currentData.atm_iv.toFixed(2)}%`}
          subtitle={`Velocity: ${(currentData.iv_velocity * 100).toFixed(2)}%`}
          color="gamma-blue"
        />
        <MetricCard 
          title="OI Velocity" 
          value={currentData.oi_velocity.toFixed(1)}
          subtitle={`Acceleration: ${currentData.oi_acceleration.toFixed(1)}`}
          color={currentData.oi_velocity > 0 ? 'gamma-green' : 'gamma-red'}
        />
      </div>

      {/* Historical Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* GEX Chart */}
        <div className="bg-dark-card rounded-lg p-4">
          <h3 className="text-lg font-semibold mb-4">Net GEX History (6 hours)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={historyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis 
                dataKey="timestamp" 
                stroke="#9CA3AF"
                tick={{ fontSize: 12 }}
                tickFormatter={(value) => new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              />
              <YAxis stroke="#9CA3AF" tick={{ fontSize: 12 }} />
              <Tooltip 
                contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                labelFormatter={(value) => new Date(value).toLocaleString()}
              />
              <Legend />
              <Line type="monotone" dataKey="net_gex" stroke="#2962FF" strokeWidth={2} dot={false} name="Net GEX" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* IV Chart */}
        <div className="bg-dark-card rounded-lg p-4">
          <h3 className="text-lg font-semibold mb-4">ATM IV History (6 hours)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={historyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis 
                dataKey="timestamp" 
                stroke="#9CA3AF"
                tick={{ fontSize: 12 }}
                tickFormatter={(value) => new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              />
              <YAxis stroke="#9CA3AF" tick={{ fontSize: 12 }} />
              <Tooltip 
                contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                labelFormatter={(value) => new Date(value).toLocaleString()}
              />
              <Legend />
              <Line type="monotone" dataKey="atm_iv" stroke="#FF4B4B" strokeWidth={2} dot={false} name="ATM IV" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* OI Velocity Chart */}
        <div className="bg-dark-card rounded-lg p-4">
          <h3 className="text-lg font-semibold mb-4">OI Velocity History</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={historyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis 
                dataKey="timestamp" 
                stroke="#9CA3AF"
                tick={{ fontSize: 12 }}
                tickFormatter={(value) => new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              />
              <YAxis stroke="#9CA3AF" tick={{ fontSize: 12 }} />
              <Tooltip 
                contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                labelFormatter={(value) => new Date(value).toLocaleString()}
              />
              <Legend />
              <Line type="monotone" dataKey="oi_velocity" stroke="#00C853" strokeWidth={2} dot={false} name="OI Velocity" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Blast Probability Chart */}
        <div className="bg-dark-card rounded-lg p-4">
          <h3 className="text-lg font-semibold mb-4">Gamma Blast Probability</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={historyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis 
                dataKey="timestamp" 
                stroke="#9CA3AF"
                tick={{ fontSize: 12 }}
                tickFormatter={(value) => new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
              />
              <YAxis stroke="#9CA3AF" tick={{ fontSize: 12 }} domain={[0, 1]} />
              <Tooltip 
                contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151' }}
                labelFormatter={(value) => new Date(value).toLocaleString()}
                formatter={(value: number) => `${(value * 100).toFixed(1)}%`}
              />
              <Legend />
              <Line type="monotone" dataKey="gamma_blast_probability" stroke="#FF9800" strokeWidth={2} dot={false} name="Blast Probability" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}

function MetricCard({ title, value, subtitle, color }: { title: string, value: string, subtitle: string, color: string }) {
  return (
    <div className="bg-dark-card rounded-lg p-4">
      <div className="text-sm text-gray-400 mb-1">{title}</div>
      <div className={`text-2xl font-bold text-${color} mb-1`}>{value}</div>
      <div className="text-xs text-gray-500">{subtitle}</div>
    </div>
  )
}
