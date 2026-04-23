import { Link, useLocation } from 'react-router-dom'
import { useState } from 'react'
import { api } from '../api'

export default function NavBar() {
  const loc = useLocation()
  const [triggering, setTriggering] = useState(false)
  const [msg, setMsg] = useState('')

  async function handleTrigger() {
    setTriggering(true)
    setMsg('')
    try {
      await api.admin.triggerScore()
      setMsg('評分觸發成功，約 30 秒後重新整理頁面查看結果')
    } catch {
      setMsg('觸發失敗，請稍後再試')
    } finally {
      setTriggering(false)
    }
  }

  const linkCls = (path: string) =>
    `px-3 py-2 rounded-md text-sm font-medium transition-colors ${
      loc.pathname === path
        ? 'bg-sky-600 text-white'
        : 'text-gray-600 hover:bg-gray-100'
    }`

  return (
    <nav className="bg-white border-b border-gray-200 sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
        <div className="flex items-center gap-1">
          <span className="font-bold text-sky-700 text-lg mr-3">📈 台股選股</span>
          <Link to="/" className={linkCls('/')}>選股</Link>
          <Link to="/macro" className={linkCls('/macro')}>宏觀</Link>
        </div>
        <div className="flex items-center gap-3">
          {msg && <span className="text-xs text-gray-500">{msg}</span>}
          <button
            onClick={handleTrigger}
            disabled={triggering}
            className="bg-sky-600 hover:bg-sky-700 disabled:opacity-50 text-white text-sm px-3 py-1.5 rounded-md transition-colors"
          >
            {triggering ? '執行中...' : '手動觸發評分'}
          </button>
        </div>
      </div>
    </nav>
  )
}
