import { BrowserRouter, Routes, Route } from 'react-router-dom'
import NavBar from './components/NavBar'
import Dashboard from './pages/Dashboard'
import StockDetail from './pages/StockDetail'
import MacroPage from './pages/Macro'

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col">
        <NavBar />
        <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/stocks/:id" element={<StockDetail />} />
            <Route path="/macro" element={<MacroPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}
