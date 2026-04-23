interface Props {
  label: string
  value: number
  max?: number
  color?: string
}

export default function ScoreBar({ label, value, max = 100, color = 'bg-sky-500' }: Props) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100))
  return (
    <div className="flex items-center gap-2">
      <span className="w-8 text-xs text-gray-500 shrink-0">{label}</span>
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-8 text-right text-xs font-medium text-gray-700">{value.toFixed(0)}</span>
    </div>
  )
}
