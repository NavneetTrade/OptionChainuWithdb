interface LiveIndicatorProps {
  isLive: boolean
}

export default function LiveIndicator({ isLive }: LiveIndicatorProps) {
  return (
    <div className="flex items-center space-x-2 bg-dark-card px-4 py-2 rounded-lg">
      <div className={`w-3 h-3 rounded-full ${isLive ? 'bg-gamma-green pulse-animation' : 'bg-gray-500'}`} />
      <span className="text-sm font-medium">
        {isLive ? 'LIVE' : 'OFFLINE'}
      </span>
    </div>
  )
}
