import { useEffect, useState } from 'react'
import { api } from '../api'
import type { MacroSnapshot } from '../types'

const PCT = (v: number | null | undefined) =>
  v != null ? `${(v * 100).toFixed(1)}%` : 'N/A'

const CHG = (v: number | null | undefined) => {
  if (v == null) return { label: 'N/A', cls: 'text-gray-400' }
  const pct = (v * 100).toFixed(2)
  return v >= 0
    ? { label: `+${pct}%`, cls: 'text-green-600' }
    : { label: `${pct}%`, cls: 'text-red-500' }
}

function ProbBar({ label, value, danger }: { label: string; value: number; danger?: boolean }) {
  const pct = Math.round(value * 100)
  const barCls = danger
    ? pct > 30 ? 'bg-red-500' : 'bg-green-500'
    : pct > 60 ? 'bg-green-600' : pct > 40 ? 'bg-amber-500' : 'bg-gray-300'
  return (
    <div className="flex items-center gap-3">
      <span className="w-36 text-sm text-gray-700 shrink-0">{label}</span>
      <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full ${barCls} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="w-12 text-right text-sm font-semibold text-gray-700">{pct}%</span>
    </div>
  )
}

function IndexRow({ label, value }: { label: string; value: number | null }) {
  const { label: chg, cls } = CHG(value)
  return (
    <div className="flex justify-between items-center py-2 border-b border-gray-50 last:border-0">
      <span className="text-sm text-gray-600">{label}</span>
      <span className={`text-sm font-semibold ${cls}`}>{chg}</span>
    </div>
  )
}

export default function MacroPage() {
  const [data, setData] = useState<MacroSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.macro.latest()
      .then(setData)
      .catch(() => setError('載入宏觀資料失敗'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="flex justify-center py-20">
      <div className="animate-spin h-8 w-8 rounded-full border-2 border-sky-500 border-t-transparent" />
    </div>
  )
  if (error || !data) return (
    <div className="text-center py-16 text-gray-500">
      <p className="text-4xl mb-3">🌐</p>
      <p>{error || '目前無宏觀資料'}</p>
    </div>
  )

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <div>
        <h1 className="text-xl font-bold text-gray-900">宏觀信號</h1>
        <p className="text-sm text-gray-400 mt-0.5">資料日期：{data.snapshot_date}</p>
      </div>

      {/* Polymarket */}
      <div className="bg-white rounded-xl shadow-sm p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">Polymarket 事件機率</h2>
        <div className="space-y-3">
          <ProbBar label="Fed 降息" value={data.fed_cut_prob} />
          <ProbBar label="NVIDIA 財報超預期" value={data.nvidia_beat_prob} />
          <ProbBar label="台海風險" value={data.taiwan_strait_prob} danger />
          <ProbBar label="中國 GDP 不及預期" value={data.china_gdp_miss_prob} danger />
          <ProbBar label="油價破 $90" value={data.oil_above_90_prob} />
        </div>
      </div>

      {/* US markets */}
      <div className="bg-white rounded-xl shadow-sm p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-3">美股 & 夜盤</h2>
        <IndexRow label="費城半導體（SOX）" value={data.sox_change} />
        <IndexRow label="那斯達克（NASDAQ）" value={data.nasdaq_change} />
        <IndexRow label="標普 500（S&P 500）" value={data.sp500_change} />
        <IndexRow label="台灣 ETF 夜盤代理（EWT）" value={data.txf_night_change} />
      </div>

      <p className="text-xs text-gray-400 text-center pb-2">
        Polymarket 為事件市場預測機率，非實際結果。美股資料由 yfinance 提供。
      </p>
    </div>
  )
}
