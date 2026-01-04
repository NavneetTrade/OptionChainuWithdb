import { useState, useEffect, useCallback } from 'react'
import Head from 'next/head'
import IndicesOverview from '../components/IndicesOverview'
import GammaBlastTable from '../components/GammaBlastTable'
import SymbolDetail from '../components/SymbolDetail'
import LiveIndicator from '../components/LiveIndicator'
import EnhancedOptionChain from '../components/EnhancedOptionChain'
import TestComponent from '../components/TestComponent'
import SentimentDashboard from '../components/SentimentDashboard'
import ITMAnalysis from '../components/ITMAnalysis'
import useWebSocket from '../hooks/useWebSocket'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws'

type TabType = 'gamma' | 'optionchain' | 'sentiment' | 'itm';

export default function Home() {
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>('NIFTY')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [activeTab, setActiveTab] = useState<TabType>('gamma')
  
  // WebSocket connection for real-time updates
  const { data: wsData, isConnected, error: wsError } = useWebSocket(WS_URL, autoRefresh)

  const tabs = [
    { id: 'gamma' as TabType, label: 'Gamma Blast', icon: '⚡' },
    { id: 'optionchain' as TabType, label: 'Option Chain', icon: '📈' },
    { id: 'sentiment' as TabType, label: 'Sentiment', icon: '📊' },
    { id: 'itm' as TabType, label: 'ITM Analysis', icon: '📉' },
  ]

  return (
    <>
      <Head>
        <title>Option Chain Analysis - Real-time Gamma Exposure</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      <main className="min-h-screen bg-dark-bg text-white">
        {/* Header */}
        <div className="bg-dark-card border-b border-gray-800 sticky top-0 z-50">
          <div className="container mx-auto px-4 py-4">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h1 className="text-3xl font-bold mb-1">
                  ⚡ Option Chain Analysis
                </h1>
                <p className="text-gray-400 text-sm">
                  Real-time Gamma Exposure & Market Analysis
                </p>
              </div>
              
              <div className="flex items-center space-x-4">
                {/* Live Indicator */}
                <LiveIndicator isLive={isConnected} />
                
                {/* Auto-refresh Toggle */}
                <button
                  onClick={() => setAutoRefresh(!autoRefresh)}
                  className={`px-4 py-2 rounded-lg transition-colors text-sm font-medium ${
                    autoRefresh 
                      ? 'bg-gamma-green text-white' 
                      : 'bg-gray-700 text-gray-400'
                  }`}
                >
                  {autoRefresh ? '🔄 Auto-refresh ON' : '⏸️ Auto-refresh OFF'}
                </button>
              </div>
            </div>

            {/* Tab Navigation */}
            <div className="flex space-x-1 border-t border-gray-800 -mb-px pt-2">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-6 py-2 font-medium text-sm transition-all rounded-t-lg ${
                    activeTab === tab.id
                      ? 'bg-dark-bg text-white border-t-2 border-blue-500'
                      : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
                  }`}
                >
                  <span className="mr-2">{tab.icon}</span>
                  {tab.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* WebSocket Error */}
        {wsError && (
          <div className="container mx-auto px-4 pt-4">
            <div className="p-4 bg-red-900/20 border border-red-500 rounded-lg">
              <p className="text-red-400">⚠️ {wsError}</p>
            </div>
          </div>
        )}

        {/* Main Dashboard Content */}
        <div className="container mx-auto px-4 py-6">
          {/* Gamma Blast Tab */}
          {activeTab === 'gamma' && (
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
          )}

          {/* Option Chain Tab */}
          {activeTab === 'optionchain' && (
            <EnhancedOptionChain />
          )}

          {/* Sentiment Dashboard Tab */}
          {activeTab === 'sentiment' && (
            <SentimentDashboard />
          )}

          {/* ITM Analysis Tab */}
          {activeTab === 'itm' && (
            <ITMAnalysis />
          )}
        </div>

        {/* Footer */}
        <footer className="mt-12 pt-6 border-t border-gray-800 text-center text-gray-500 pb-6">
          <p className="text-sm">
            Powered by FastAPI + Next.js | Real-time WebSocket Updates | 
            Data updates every {autoRefresh ? '5' : '∞'} seconds
          </p>
        </footer>
      </main>
    </>
  )
}
