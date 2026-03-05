# CLAUDE.md — Instructions for Claude Code

## 你的任務
請閱讀 `PRD.md`，依照其中的 System Design 從零建立完整的 `taiwan-stock-bot` 專案。

## 執行方式
1. 先完整閱讀 `PRD.md`
2. 依照 **Section 8.1 Build Order** 的順序逐步實作
3. 每個檔案寫完後繼續下一個，不要跳過
4. 實作完成後執行 `docker compose up` 確認所有服務可正常啟動

## 驗收標準
- [ ] `docker compose up` 啟動無錯誤
- [ ] `GET /api/v1/health` 回傳 200
- [ ] `alembic upgrade head` 成功建立所有資料表
- [ ] `pytest tests/` 全數通過
- [ ] `POST /api/v1/admin/trigger-score` 可手動觸發選股並寫入 DB
