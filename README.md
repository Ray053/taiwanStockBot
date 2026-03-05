# 🤖 Taiwan Stock AI Bot

> ⚠️ **This is a test/demo project for learning purposes. Not financial advice.**

全自動台股選股系統，整合 FinMind 籌碼資料、技術指標計算與 Polymarket 宏觀預測市場信號，每日產出多因子加權評分的選股清單，並透過 LINE 推播通知。

---

## Features

- **多因子評分** — 技術面 + 法人籌碼 + 融資融券 + Polymarket 宏觀信號
- **每日自動排程** — APScheduler 定時抓資料、算分、推播
- **LINE Notify 推播** — 收盤後自動傳送 Top 10 選股
- **REST API** — FastAPI 提供完整查詢介面
- **全 Docker 化** — 一行指令啟動所有服務

---

## Tech Stack

| 層 | 技術 |
|----|------|
| API | FastAPI + Uvicorn |
| 資料庫 | PostgreSQL 15 |
| 快取 / 佇列 | Redis 7 |
| ORM / Migration | SQLAlchemy 2 + Alembic |
| 排程 | APScheduler (Asia/Taipei) |
| 資料來源 | FinMind REST API、Polymarket Gamma API |
| 推播 | LINE Notify |
| 容器化 | Docker Compose |

---

## Quick Start

### 前置需求
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) 已安裝

### 步驟

```bash
# 1. Clone 專案
git clone https://github.com/Ray053/taiwanStockBot.git
cd taiwanStockBot

# 2. 建立環境變數檔
cp .env.example .env

# 3. 編輯 .env，填入你的 token（見下方說明）
nano .env

# 4. 啟動所有服務
docker compose up -d

# 5. 確認 API 正常
curl http://localhost:8000/api/v1/health
# 預期回應: {"status":"ok","service":"taiwan-stock-bot"}
```

---

## Environment Variables

複製 `.env.example` 為 `.env` 後填入以下欄位：

| 變數 | 說明 | 取得方式 |
|------|------|---------|
| `FINMIND_API_TOKEN` | FinMind API Token | [finmindtrade.com](https://finmindtrade.com) 免費註冊 |
| `LINE_NOTIFY_TOKEN` | LINE Notify Token | [notify-bot.line.me/my](https://notify-bot.line.me/my/) → 發行權杖 |
| `ADMIN_API_KEY` | 管理介面保護密鑰 | 自行設定任意強密碼 |

> 其餘 DB / Redis 連線設定已預設指向 Docker 內部服務，不需修改。

---

## API Endpoints

Base URL: `http://localhost:8000/api/v1`

| Method | Endpoint | 說明 |
|--------|----------|------|
| GET | `/health` | 健康檢查 |
| GET | `/scores/today` | 今日 Top N 選股（`?limit=10`） |
| GET | `/scores/{date}` | 指定日期選股（YYYY-MM-DD） |
| GET | `/scores/stock/{stock_id}` | 個股歷史評分（`?days=30`） |
| GET | `/stocks/{stock_id}/kline` | K線 + 技術指標 |
| GET | `/stocks/{stock_id}/institutional` | 三大法人買賣超 |
| GET | `/stocks/{stock_id}/margin` | 融資融券 |
| GET | `/macro/latest` | 最新 Polymarket 快照 |
| POST | `/admin/trigger-score` | 手動觸發選股（需 `X-API-Key` header） |
| POST | `/admin/refresh-polymarket` | 手動更新宏觀快照（需 `X-API-Key` header） |

互動式文件：`http://localhost:8000/docs`

---

## Scoring Logic

| 因子 | 權重 | 滿分條件 |
|------|------|---------|
| 技術面 | 35% | 均線多頭排列 + RSI 健康 + MACD 金叉 + 量能放大 |
| 法人籌碼 | 35% | 外資 + 投信 + 自營商全買超 |
| 融資融券 | 10% | 融資融券均減少（籌碼最乾淨） |
| 宏觀信號 | 20% | Polymarket 機率加減分（依產業別） |

---

## Daily Schedule (Asia/Taipei)

| 時間 | 任務 |
|------|------|
| 06:00 | 抓取 Polymarket 宏觀快照 |
| 08:30 | 抓取三大法人、融資融券資料 |
| 09:05 | 計算技術指標，更新快取 |
| 14:05 | 執行多因子評分，寫入 DB |
| 14:30 | 推播 LINE Notify Top 10 |
| 23:00 | 美股盤後更新（預留） |

---

## Services

| 服務 | Port | 說明 |
|------|------|------|
| API | 8000 | FastAPI 主服務 |
| PostgreSQL | 5432 | 主資料庫 |
| Redis | 6379 | 快取 |
| pgAdmin | 5050 | DB 管理介面（帳號: admin@stockbot.local / admin） |

---

## Development

```bash
# 執行測試
pytest tests/ -v

# 只跑單元測試
pytest tests/test_signal_engine.py tests/test_scoring_engine.py -v

# 手動觸發選股
curl -X POST http://localhost:8000/api/v1/admin/trigger-score \
  -H "X-API-Key: your_admin_key"
```

---

## Disclaimer

> ⚠️ **本專案為學習測試用途，所有選股結果僅供參考，不構成任何投資建議。投資有風險，請自行評估。**
