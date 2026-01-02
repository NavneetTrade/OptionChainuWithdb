import { useState, useEffect, useCallback } from 'react'
import Head from 'next/head'
import IndicesOverview from '../components/IndicesOverview'
import GammaBlastTable from '../components/GammaBlastTable'
import SymbolDetail from '../components/SymbolDetail'
import LiveIndicator from '../components/LiveIndicator'
import useWebSocket from '../hooks/useWebSocket'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws'

export default function Home() {
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>('NIFTY')
  const [autoRefresh, setAutoRefresh] = useState(true)
  
  // WebSocket connection for real-time updates
  const { data: wsData, isConnected, error: wsError } = useWebSocket(WS_URL, autoRefresh)

  return (
    <>
      <Head>
        <title>Option Chain Analysis - Real-time Gamma Exposure</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      <main className="min-h-screen bg-dark-bg text-white p-4">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold mb-2">
              ⚡ Option Chain Analysis
            </h1>
            <p className="text-gray-400">
              Real-time Gamma Exposure & Blast Detection
            </p>
          </div>
          
          <div className="flex items-center space-x-4">
            {/* Live Indicator */}
            <LiveIndicator isLive={isConnected} />
            
            {/* Auto-refresh Toggle */}
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`px-4 py-2 rounded-lg transition-colors ${
                autoRefresh 
                  ? 'bg-gamma-green text-white' 
                  : 'bg-dark-card text-gray-400'
              }`}
            >
              {autoRefresh ? '🔄 Auto-refresh ON' : '⏸️ Auto-refresh OFF'}
            </button>
          </div>
        </div>

        {/* WebSocket Error */}
        {wsError && (
          <div className="mb-4 p-4 bg-red-900/20 border border-red-500 rounded-lg">
            <p className="text-red-400">⚠️ {wsError}</p>
          </div>
        )}

        {/* Main Dashboard Grid */}
        <div className="space-y-6">
          {/* Indices Overview */}
          <section>
            <h2 className="text-2xl font-semibold mb-4">📊 Indices Overview</h2>
            <IndicesOverview 
              onSymbolClick={setSelectedSymbol}
              selectedSymbol={selectedSymbol}
              liveData={wsData}
            />
          </section>

          {/* Top Gamma Blasts */}
          <section>
            <h2 className="text-2xl font-semibold mb-4">🔥 Top Gamma Blasts</h2>
            <GammaBlastTable 
              onSymbolClick={setSelectedSymbol}
              liveData={wsData}
            />
          </section>

          {/* Symbol Detail View */}
          {selectedSymbol && (
            <section>
              <h2 className="text-2xl font-semibold mb-4">
                📈 {selectedSymbol} - Detailed Analysis
              </h2>
              <SymbolDetail 
                symbol={selectedSymbol}
                liveData={wsData?.find((d: any) => d.symbol === selectedSymbol)}
              />
            </section>
          )}
        </div>

        {/* Footer */}
        <footer className="mt-12 pt-6 border-t border-gray-800 text-center text-gray-500">
          <p>
            Powered by FastAPI + Next.js | Real-time WebSocket Updates | 
            Data updates every {autoRefresh ? '5' : '∞'} seconds
          </p>
        </footer>
      </main>
    </>
  )
}
