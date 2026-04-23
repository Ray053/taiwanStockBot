import { useEffect, useState } from 'react'
import { api } from '../api'
import type { ScreeningResult } from '../types'
import CategoryCard from '../components/CategoryCard'

export default function Dashboard() {
  const [data, setData] = useState<ScreeningResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.screening.today()
      .then(setData)
      .catch(() => setError('載入失敗，請稍後再試'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingState />
  if (error) return <ErrorState msg={error} />
  if (!data || Object.keys(data.categories).length === 0) {
    return <EmptyState />
  }

  return (
    <div>
      <div className="flex items-baseline justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-gray-900">動能選股</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {data.score_date} · 共分析 {data.total_stocks} 檔股票
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Object.entries(data.categories).map(([key, cat]) => (
          <CategoryCard key={key} catKey={key} data={cat} />
        ))}
      </div>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="flex justify-center items-center py-20">
      <div className="animate-spin rounded-full h-8 w-8 border-2 border-sky-500 border-t-transparent" />
      <span className="ml-3 text-gray-500">載入中...</span>
    </div>
  )
}

function ErrorState({ msg }: { msg: string }) {
  return (
    <div className="text-center py-16 text-red-500">
      <p className="text-4xl mb-3">⚠️</p>
      <p>{msg}</p>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="text-center py-16 text-gray-400">
      <p className="text-5xl mb-4">📭</p>
      <p className="text-lg font-medium text-gray-600">今日尚無選股資料</p>
      <p className="text-sm mt-1">點選右上角「手動觸發評分」立即執行選股</p>
    </div>
  )
}
