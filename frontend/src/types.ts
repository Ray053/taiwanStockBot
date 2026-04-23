export interface StockInCategory {
  stock_id: string
  stock_name: string
  sector: string
  total_score: number
  tech_score: number
  inst_score: number
  trust_net: number | null
  foreign_net: number | null
  trust_consec: number
  foreign_consec: number
  reasons: string[]
}

export interface Category {
  name: string
  emoji: string
  description: string
  stocks: StockInCategory[]
}

export interface ScreeningResult {
  score_date: string
  categories: Record<string, Category>
  total_stocks: number
}

export interface DayScore {
  score_date: string
  rank: number
  total_score: number
  tech_score: number
  inst_score: number
  margin_score: number
  macro_score: number
  reasons: string[]
  signals: Record<string, unknown>
  foreign_net: number | null
  trust_net: number | null
}

export interface StockHistory {
  stock_id: string
  stock_name: string
  sector: string
  history: DayScore[]
  categories: { key: string; name: string; emoji: string }[]
}

export interface MacroSnapshot {
  snapshot_date: string
  fed_cut_prob: number
  nvidia_beat_prob: number
  taiwan_strait_prob: number
  china_gdp_miss_prob: number
  oil_above_90_prob: number
  txf_night_change: number | null
  sox_change: number | null
  nasdaq_change: number | null
  sp500_change: number | null
}
