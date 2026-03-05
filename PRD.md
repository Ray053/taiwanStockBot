# Taiwan Stock AI Bot — PRD & System Design
> Version 1.0 | FinMind API × Polymarket × FastAPI × PostgreSQL

---

## 1. Product Overview

### 1.1 目標
建立一套全自動化台股選股系統，整合 FinMind 籌碼資料、技術指標計算與 Polymarket 宏觀預測市場信號，每日產出多因子加權評分的選股清單，並透過 Line / Telegram 推播通知。

### 1.2 核心差異化
| 面向 | 傳統工具（艾德恩/三竹） | 本系統 |
|------|----------------------|--------|
| 資料整合 | 純技術面 / 籌碼 | 技術 + 籌碼 + Polymarket 宏觀 |
| 策略彈性 | 平台語法限制 | 純 Python，無限制 |
| 跨市場信號 | 無 | 美股財報預期 → 台股 AI 族群 |
| 宏觀濾網 | 無 | Fed/地緣政治/油價機率 |
| 部署 | 訂閱制雲端 | 自架 Docker，策略不外洩 |

### 1.3 使用者故事
- 身為投資人，我希望每天收盤後收到前 10 名選股推薦，包含得分理由
- 身為投資人，我希望系統在 Fed 降息預期升高時，自動加權金融股評分
- 身為投資人，我希望可以查詢個股的歷史評分趨勢
- 身為投資人，我希望系統在台海風險上升時，自動降低電子出口股評分

---

## 2. System Architecture

### 2.1 整體架構（四層）

```
┌─────────────────────────────────────────────────────────┐
│                  DATA INGESTION LAYER                    │
│   FinMind SDK      Polymarket API      TWSE API          │
│   K線/法人/融資    宏觀事件機率         大盤指數           │
└────────────────────────┬────────────────────────────────┘
                         │ Redis Queue
┌────────────────────────▼────────────────────────────────┐
│                   PROCESSING LAYER                       │
│   Signal Engine         Scoring Engine    APScheduler   │
│   MA/RSI/MACD/KD        多因子加權評分     定時任務       │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│                    STORAGE LAYER                         │
│          PostgreSQL (主資料)    Redis (快取)              │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────┐
│                    OUTPUT LAYER                          │
│        FastAPI REST API       LINE / Telegram Notifier  │
└─────────────────────────────────────────────────────────┘
```

### 2.2 服務清單（Docker Compose）
| 服務名稱 | Image | Port | 職責 |
|---------|-------|------|------|
| api | python:3.11-slim | 8000 | FastAPI 主服務 |
| scheduler | python:3.11-slim | - | APScheduler 排程器（獨立 process） |
| postgres | postgres:15 | 5432 | 主資料庫 |
| redis | redis:7-alpine | 6379 | 快取 + 任務佇列 |
| pgadmin | dpage/pgadmin4 | 5050 | DB 管理介面（開發用） |

### 2.3 每日排程時間軸
| 時間 | 任務 | 資料來源 | 說明 |
|------|------|---------|------|
| 06:00 | fetch_polymarket | Polymarket API | 抓取宏觀信號快照並存入 DB |
| 08:30 | fetch_institutional | FinMind API | 前日三大法人、融資融券 |
| 09:05 | compute_signals | FinMind K線 | 計算技術指標，更新 Redis 快取 |
| 14:05 | run_scoring | DB + Redis | 跑多因子評分，輸出 Top 10 |
| 14:30 | send_notification | Scoring DB | 推播 LINE / Telegram |
| 23:00 | fetch_us_afterhours | yfinance | 美股盤後，更新次日宏觀信號 |

---

## 3. Database Schema

### 3.1 stocks
```sql
CREATE TABLE stocks (
    stock_id     VARCHAR(10) PRIMARY KEY,
    stock_name   VARCHAR(50) NOT NULL,
    sector       VARCHAR(30),             -- 產業別（半導體/金融/航運...）
    market       VARCHAR(10) DEFAULT 'TWSE',
    is_active    BOOLEAN DEFAULT TRUE,
    created_at   TIMESTAMP DEFAULT NOW()
);
```

### 3.2 daily_kline
```sql
CREATE TABLE daily_kline (
    id           SERIAL PRIMARY KEY,
    stock_id     VARCHAR(10) REFERENCES stocks(stock_id),
    trade_date   DATE NOT NULL,
    open         NUMERIC(10,2),
    high         NUMERIC(10,2),
    low          NUMERIC(10,2),
    close        NUMERIC(10,2),
    volume       BIGINT,
    ma5          NUMERIC(10,2),
    ma20         NUMERIC(10,2),
    ma60         NUMERIC(10,2),
    rsi14        NUMERIC(6,2),
    macd         NUMERIC(10,4),
    macd_signal  NUMERIC(10,4),
    created_at   TIMESTAMP DEFAULT NOW(),
    UNIQUE (stock_id, trade_date)
);
CREATE INDEX idx_kline_date ON daily_kline(trade_date DESC);
CREATE INDEX idx_kline_stock ON daily_kline(stock_id, trade_date DESC);
```

### 3.3 institutional_investors
```sql
CREATE TABLE institutional_investors (
    id           SERIAL PRIMARY KEY,
    stock_id     VARCHAR(10) REFERENCES stocks(stock_id),
    trade_date   DATE NOT NULL,
    foreign_net  BIGINT,   -- 外資買賣超（張）
    trust_net    BIGINT,   -- 投信買賣超（張）
    dealer_net   BIGINT,   -- 自營商買賣超（張）
    total_net    BIGINT,   -- 三大法人合計
    UNIQUE (stock_id, trade_date)
);
CREATE INDEX idx_inst_stock ON institutional_investors(stock_id, trade_date DESC);
```

### 3.4 margin_trading
```sql
CREATE TABLE margin_trading (
    id                SERIAL PRIMARY KEY,
    stock_id          VARCHAR(10) REFERENCES stocks(stock_id),
    trade_date        DATE NOT NULL,
    margin_balance    BIGINT,  -- 融資餘額（張）
    margin_change     BIGINT,  -- 融資增減
    short_balance     BIGINT,  -- 融券餘額（張）
    short_change      BIGINT,  -- 融券增減
    UNIQUE (stock_id, trade_date)
);
```

### 3.5 macro_snapshots（Polymarket）
```sql
CREATE TABLE macro_snapshots (
    id                   SERIAL PRIMARY KEY,
    snapshot_date        DATE NOT NULL UNIQUE,
    fed_cut_prob         NUMERIC(5,4),  -- Fed 2025 降息機率
    nvidia_beat_prob     NUMERIC(5,4),  -- NVIDIA 財報超預期機率
    taiwan_strait_prob   NUMERIC(5,4),  -- 台海風險機率
    china_gdp_miss_prob  NUMERIC(5,4),  -- 中國 GDP 不及預期
    oil_above_90_prob    NUMERIC(5,4),  -- 油價 > 90 機率
    created_at           TIMESTAMP DEFAULT NOW()
);
```

### 3.6 daily_scores
```sql
CREATE TABLE daily_scores (
    id             SERIAL PRIMARY KEY,
    score_date     DATE NOT NULL,
    stock_id       VARCHAR(10) REFERENCES stocks(stock_id),
    total_score    NUMERIC(6,2),
    tech_score     NUMERIC(6,2),
    inst_score     NUMERIC(6,2),
    margin_score   NUMERIC(6,2),
    macro_score    NUMERIC(6,2),
    rank           INTEGER,
    breakdown      JSONB,         -- { "reasons": ["✅ 多頭排列", "✅ 外資買超"] }
    created_at     TIMESTAMP DEFAULT NOW(),
    UNIQUE (score_date, stock_id)
);
CREATE INDEX idx_scores_date ON daily_scores(score_date DESC, total_score DESC);
```

---

## 4. Backend API Endpoints

Base URL: `http://localhost:8000/api/v1`

### 4.1 選股
| Method | Endpoint | 說明 | Query Params |
|--------|----------|------|-------------|
| GET | `/scores/today` | 今日 Top N 選股 | `limit=10` |
| GET | `/scores/{date}` | 指定日期選股（YYYY-MM-DD） | `limit=10` |
| GET | `/scores/stock/{stock_id}` | 個股歷史評分趨勢 | `days=30` |

### 4.2 籌碼 / 技術面
| Method | Endpoint | 說明 | Query Params |
|--------|----------|------|-------------|
| GET | `/stocks/{stock_id}/kline` | K線 + 技術指標 | `days=60` |
| GET | `/stocks/{stock_id}/institutional` | 三大法人買賣超 | `days=30` |
| GET | `/stocks/{stock_id}/margin` | 融資融券趨勢 | `days=30` |
| GET | `/stocks/{stock_id}/detail` | 個股完整快照 | - |

### 4.3 宏觀信號
| Method | Endpoint | 說明 |
|--------|----------|------|
| GET | `/macro/latest` | 最新 Polymarket 快照 |
| GET | `/macro/history` | 歷史宏觀信號（近 30 日） |

### 4.4 管理
| Method | Endpoint | 說明 | Auth |
|--------|----------|------|------|
| POST | `/admin/trigger-score` | 手動觸發選股計算 | `X-API-Key` header |
| POST | `/admin/refresh-polymarket` | 手動更新 Polymarket 快照 | `X-API-Key` header |
| GET | `/health` | 服務健康檢查 | - |

### 4.5 Response Schema 範例
```json
// GET /scores/today
[
  {
    "stock_id": "2330",
    "stock_name": "台積電",
    "sector": "半導體",
    "total_score": 87.5,
    "tech_score": 95.0,
    "inst_score": 80.0,
    "margin_score": 70.0,
    "macro_score": 90.0,
    "rank": 1,
    "breakdown": {
      "reasons": [
        "✅ 均線多頭排列",
        "✅ RSI 強勢健康 (62.3)",
        "✅ 外資買超 +5,234 張",
        "✅ NVIDIA 財報超預期機率高 (72%)"
      ]
    }
  }
]
```

---

## 5. Scoring Engine

### 5.1 因子權重
| 因子 | 權重 | 說明 |
|------|------|------|
| 技術面 | 35% | MA排列、RSI、MACD、量能 |
| 法人籌碼 | 35% | 外資、投信、自營商買賣超 |
| 融資融券 | 10% | 籌碼乾淨度 |
| 宏觀信號 | 20% | Polymarket 機率加減分 |

### 5.2 技術面評分（滿分 100）
| 條件 | 得分 |
|------|------|
| MA5 > MA20 > MA60 多頭排列 | +40 |
| RSI 50~70 | +25 |
| MACD 上穿 Signal 線（金叉當日） | +20 |
| 當日量 > 20日均量 × 1.5 | +15 |

### 5.3 法人籌碼評分（滿分 100）
| 條件 | 得分 |
|------|------|
| 外資買超 > 0 | +40 |
| 投信買超 > 0 | +40 |
| 自營商買超 > 0 | +20 |

### 5.4 融資融券評分（滿分 100）
| 條件 | 得分 |
|------|------|
| 融資餘額減少 AND 融券餘額減少 | 100（籌碼最乾淨） |
| 融資減少 OR 融券減少（其一） | 60 |
| 兩者皆增加 | 20 |

### 5.5 Polymarket 宏觀加減分（基準 50 分）
| 市場事件 | 觸發條件 | 適用 sector | 加減分 |
|---------|---------|------------|--------|
| Fed 2025 降息 | 機率 > 65% | 金融、營建 | +20 |
| NVIDIA 財報超預期 | 機率 > 60% | 半導體、電子 | +20 |
| 台海風險 | 機率 > 25% | 半導體、電子 | -30 |
| 中國 GDP 不及預期 | 機率 > 50% | 傳產、化工 | -15 |
| 油價 > $90 | 機率 > 55% | 航運、塑化 | +10 |

---

## 6. Project Structure

```
taiwan-stock-bot/
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py
├── app/
│   ├── main.py                  # FastAPI app factory, startup events
│   ├── config.py                # pydantic-settings, 讀取 .env
│   ├── database.py              # SQLAlchemy engine, SessionLocal, get_db
│   ├── models/
│   │   ├── __init__.py
│   │   ├── stock.py
│   │   ├── kline.py
│   │   ├── institutional.py
│   │   ├── margin.py
│   │   ├── macro_snapshot.py
│   │   └── daily_score.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── stock.py
│   │   ├── score.py
│   │   └── macro.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── scores.py
│   │   ├── stocks.py
│   │   ├── macro.py
│   │   └── admin.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── finmind_client.py    # FinMind SDK wrapper，含 Redis 快取
│   │   ├── polymarket_client.py # Polymarket gamma API wrapper
│   │   ├── signal_engine.py     # 技術指標：MA/RSI/MACD/Volume
│   │   ├── scoring_engine.py    # 多因子加權評分主邏輯
│   │   └── notifier.py          # LINE Notify + Telegram Bot
│   └── scheduler/
│       ├── __init__.py
│       ├── scheduler.py         # APScheduler 初始化，timezone=Asia/Taipei
│       └── tasks.py             # 各定時任務函式
├── scheduler_main.py            # scheduler 獨立入口（給 docker scheduler service）
└── tests/
    ├── conftest.py
    ├── test_signal_engine.py
    ├── test_scoring_engine.py
    └── test_api.py
```

---

## 7. Environment Variables（.env.example）

```env
# PostgreSQL
DATABASE_URL=postgresql://stockbot:password@postgres:5432/stockbot

# Redis
REDIS_URL=redis://redis:6379/0

# FinMind
FINMIND_API_TOKEN=your_finmind_token_here

# LINE Notify
LINE_NOTIFY_TOKEN=your_line_notify_token

# Telegram
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Admin API Security
ADMIN_API_KEY=change_this_to_a_secure_random_string

# Scoring Weights (must sum to 1.0)
WEIGHT_TECHNICAL=0.35
WEIGHT_INSTITUTIONAL=0.35
WEIGHT_MARGIN=0.10
WEIGHT_MACRO=0.20

# Polymarket market slugs (update if slugs change)
POLY_FED_CUT_SLUG=will-the-fed-cut-rates-in-2025
POLY_NVIDIA_BEAT_SLUG=will-nvidia-beat-q1-2025-earnings
POLY_TAIWAN_STRAIT_SLUG=taiwan-strait-incident-2025
POLY_CHINA_GDP_SLUG=will-china-miss-gdp-target-2025
POLY_OIL_90_SLUG=will-oil-be-above-90-end-of-2025

# App
APP_ENV=development
LOG_LEVEL=INFO
```

---

## 8. Key Implementation Notes for Claude Code

### 8.1 Build Order（依序實作）
1. `docker-compose.yml` + `.env.example` — 確保所有服務可啟動
2. `app/config.py` + `app/database.py` — 環境變數與 DB 連線
3. `app/models/` 全部 ORM models + `alembic` migration
4. `app/services/finmind_client.py` — 驗證資料可正確抓取
5. `app/services/polymarket_client.py` — 驗證機率數值
6. `app/services/signal_engine.py` + unit tests
7. `app/services/scoring_engine.py` + unit tests
8. `app/routers/` 全部 API endpoints
9. `app/scheduler/tasks.py` + `scheduler.py`
10. `app/services/notifier.py`

### 8.2 Critical Rules
- FinMind 所有寫入用 `INSERT ... ON CONFLICT (stock_id, trade_date) DO UPDATE`
- Redis key 格式：`finmind:{stock_id}:{data_type}:{date}`，TTL = 3600 秒
- Polymarket client 找不到 market slug 時回傳 `0.5`（中性值），不拋例外
- APScheduler 必須設定 `timezone='Asia/Taipei'`
- FastAPI startup event 執行 `alembic upgrade head`
- Scoring Engine 的宏觀加減分需先查 `stocks.sector` 再套用對應規則
- 所有對外 API call 加 timeout=15 秒 + retry 3 次

### 8.3 Polymarket API
```
Base URL: https://gamma-api.polymarket.com
Endpoint: GET /markets?slug={slug}
Response: outcomePrices[0] = YES 機率（0~1 的字串）
```

### 8.4 FinMind 需使用的 Dataset
| Dataset | 說明 |
|---------|------|
| `TaiwanStockPrice` | 日K線 |
| `TaiwanStockInstitutionalInvestorsBuySell` | 三大法人買賣超 |
| `TaiwanStockMarginPurchaseShortSale` | 融資融券 |
| `TaiwanStockInfo` | 股票基本資料（取得 sector） |
