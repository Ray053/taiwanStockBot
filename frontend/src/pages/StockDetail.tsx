import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api'
import type { StockHistory, DayScore } from '../types'
import ScoreBar from '../components/ScoreBar'

const SCORE_COLOR = (s: number) =>
  s >= 70 ? 'text-green-600' : s >= 45 ? 'text-amber-600' : 'text-red-500'

const TREND_ICON = (curr: number, prev?: number) => {
  if (prev == null) return ''
  return curr > prev ? '▲' : curr < prev ? '▼' : '─'
}

export default function StockDetail() {
  const { id } = useParams<{ id: string }>()
  const [data, setData] = useState<StockHistory | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!id) return
    api.screening.stock(id)
      .then(setData)
      .catch(() => setError('找不到個股資料'))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return (
    <div className="flex justify-center py-20">
      <div className="animate-spin h-8 w-8 rounded-full border-2 border-sky-500 border-t-transparent" />
    </div>
  )
  if (error || !data) return (
    <div className="text-center py-16 text-gray-500">
      <p>{error || '無資料'}</p>
      <Link to="/" className="text-sky-600 text-sm mt-2 inline-block">← 返回選股</Link>
    </div>
  )

  const latest: DayScore | undefined = data.history[0]

  return (
    <div className="max-w-2xl mx-auto">
      <Link to="/" className="text-sky-600 text-sm mb-4 inline-block">← 返回選股</Link>

      {/* Header */}
      <div className="bg-white rounded-xl shadow-sm p-5 mb-4">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {data.stock_id}
              <span className="ml-2 text-lg font-medium text-gray-600">{data.stock_name}</span>
            </h1>
            <p className="text-sm text-gray-400 mt-0.5">{data.sector}</p>
          </div>
          {latest && (
            <div className="text-right">
              <p className={`text-3xl font-bold ${SCORE_COLOR(latest.total_score)}`}>
                {latest.total_score.toFixed(1)}
              </p>
              <p className="text-xs text-gray-400">排名 #{latest.rank}</p>
            </div>
          )}
        </div>

        {/* Score breakdown */}
        {latest && (
          <div className="mt-4 space-y-2">
            <ScoreBar label="技術" value={latest.tech_score} color="bg-sky-500" />
            <ScoreBar label="法人" value={latest.inst_score} color="bg-purple-500" />
            <ScoreBar label="籌碼" value={latest.margin_score} color="bg-amber-500" />
            <ScoreBar label="宏觀" value={latest.macro_score} color="bg-green-500" />
          </div>
        )}
      </div>

      {/* Categories */}
      {data.categories.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm p-5 mb-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">出現策略類別</h2>
          <div className="flex flex-wrap gap-2">
            {data.categories.map(c => (
              <span
                key={c.key}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-sky-50 text-sky-700 text-xs font-medium"
              >
                {c.emoji} {c.name}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Reasons */}
      {latest?.reasons && latest.reasons.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm p-5 mb-4">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">選股原因</h2>
          <ul className="space-y-1.5">
            {latest.reasons.map((r, i) => (
              <li key={i} className="text-sm text-gray-700">{r}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Historical trend */}
      {data.history.length > 1 && (
        <div className="bg-white rounded-xl shadow-sm p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">近期走勢</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-gray-400 border-b border-gray-100">
                <th className="pb-2 text-left font-medium">日期</th>
                <th className="pb-2 text-right font-medium">總分</th>
                <th className="pb-2 text-right font-medium">排名</th>
                <th className="pb-2 text-right font-medium">技術</th>
                <th className="pb-2 text-right font-medium">法人</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {data.history.map((row, i) => {
                const prev = data.history[i + 1]
                const trend = TREND_ICON(row.total_score, prev?.total_score)
                const trendCls = trend === '▲' ? 'text-green-500' : trend === '▼' ? 'text-red-400' : 'text-gray-300'
                return (
                  <tr key={row.score_date} className={i === 0 ? 'font-medium' : ''}>
                    <td className="py-2 text-gray-600">{row.score_date}</td>
                    <td className="py-2 text-right">
                      <span className={SCORE_COLOR(row.total_score)}>{row.total_score.toFixed(1)}</span>
                      <span className={`ml-1 text-xs ${trendCls}`}>{trend}</span>
                    </td>
                    <td className="py-2 text-right text-gray-500">#{row.rank}</td>
                    <td className="py-2 text-right text-gray-500">{row.tech_score.toFixed(0)}</td>
                    <td className="py-2 text-right text-gray-500">{row.inst_score.toFixed(0)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
