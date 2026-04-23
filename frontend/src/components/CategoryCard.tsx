import { useNavigate } from 'react-router-dom'
import type { Category } from '../types'

const ACCENT: Record<string, string> = {
  volume_momentum: 'border-orange-400',
  trust_consecutive: 'border-blue-400',
  trust_big_buy: 'border-blue-500',
  foreign_big_buy: 'border-purple-500',
  both_buying: 'border-purple-400',
  kd_golden_cross: 'border-green-500',
  rsi_recovery: 'border-emerald-500',
  ma_breakout: 'border-indigo-500',
}

const SCORE_COLOR = (s: number) =>
  s >= 70 ? 'text-green-600' : s >= 45 ? 'text-amber-600' : 'text-red-500'

interface Props {
  catKey: string
  data: Category
}

export default function CategoryCard({ catKey, data }: Props) {
  const nav = useNavigate()
  const accent = ACCENT[catKey] ?? 'border-gray-300'

  return (
    <div className={`bg-white rounded-xl shadow-sm border-l-4 ${accent} overflow-hidden`}>
      <div className="px-4 pt-4 pb-2">
        <div className="flex items-baseline gap-2">
          <span className="text-xl">{data.emoji}</span>
          <h3 className="font-semibold text-gray-800">{data.name}</h3>
          <span className="ml-auto text-xs text-gray-400">{data.stocks.length} 檔</span>
        </div>
        <p className="text-xs text-gray-500 mt-0.5">{data.description}</p>
      </div>

      {data.stocks.length === 0 ? (
        <p className="px-4 pb-4 text-sm text-gray-400">今日無符合個股</p>
      ) : (
        <ul className="divide-y divide-gray-50">
          {data.stocks.map(s => (
            <li
              key={s.stock_id}
              onClick={() => nav(`/stocks/${s.stock_id}`)}
              className="px-4 py-2.5 hover:bg-gray-50 cursor-pointer flex items-center gap-3"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-1.5">
                  <span className="font-mono text-sm font-medium text-gray-800">{s.stock_id}</span>
                  <span className="text-sm text-gray-600 truncate">{s.stock_name}</span>
                  <span className="ml-auto text-xs text-gray-400 shrink-0">{s.sector}</span>
                </div>
                <div className="flex gap-3 mt-0.5 text-xs text-gray-500">
                  {s.foreign_net != null && s.foreign_net > 0 && (
                    <span className="text-purple-600">外資 +{s.foreign_net.toLocaleString()}</span>
                  )}
                  {s.trust_net != null && s.trust_net > 0 && (
                    <span className="text-blue-600">投信 +{s.trust_net.toLocaleString()}</span>
                  )}
                  {s.trust_consec >= 3 && (
                    <span className="text-blue-400">連{s.trust_consec}日</span>
                  )}
                </div>
              </div>
              <span className={`text-base font-bold shrink-0 ${SCORE_COLOR(s.total_score)}`}>
                {s.total_score.toFixed(0)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
