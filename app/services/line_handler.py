"""LINE Bot message handler — keyword parsing & reply building."""
import logging
import re
from datetime import date, timedelta

import httpx

from app.config import settings
from app.database import SessionLocal
from app.models.daily_score import DailyScore
from app.models.stock import Stock
from app.models.macro_snapshot import MacroSnapshot

logger = logging.getLogger(__name__)

REPLY_URL = "https://api.line.me/v2/bot/message/reply"
TIMEOUT = 10

# ── Quick Reply buttons appended to every reply ───────────────────────────────

QUICK_REPLY = {
    "items": [
        {
            "type": "action",
            "action": {"type": "message", "label": "今日選股", "text": "今日選股"},
        },
        {
            "type": "action",
            "action": {"type": "message", "label": "宏觀信號", "text": "宏觀"},
        },
        {
            "type": "action",
            "action": {"type": "message", "label": "使用說明", "text": "說明"},
        },
    ]
}


# ── Reply sender ──────────────────────────────────────────────────────────────

def _reply(reply_token: str, messages: list[dict]) -> None:
    token = settings.line_channel_access_token
    if not token:
        logger.warning("LINE channel access token not set, skip reply")
        return
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                REPLY_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"replyToken": reply_token, "messages": messages},
            )
            resp.raise_for_status()
    except Exception as e:
        logger.error(f"LINE reply error: {e}")


def _text_msg(text: str, quick_reply: bool = True) -> dict:
    msg: dict = {"type": "text", "text": text}
    if quick_reply:
        msg["quickReply"] = QUICK_REPLY
    return msg


# ── Query helpers ─────────────────────────────────────────────────────────────

def _get_today_top(limit: int = 10) -> list[dict]:
    db = SessionLocal()
    try:
        today = date.today()
        scores = (
            db.query(DailyScore, Stock)
            .join(Stock, DailyScore.stock_id == Stock.stock_id)
            .filter(DailyScore.score_date == today)
            .order_by(DailyScore.rank)
            .limit(limit)
            .all()
        )
        if not scores:
            yesterday = today - timedelta(days=1)
            scores = (
                db.query(DailyScore, Stock)
                .join(Stock, DailyScore.stock_id == Stock.stock_id)
                .filter(DailyScore.score_date == yesterday)
                .order_by(DailyScore.rank)
                .limit(limit)
                .all()
            )
        return [
            {
                "rank": s.rank,
                "stock_id": s.stock_id,
                "stock_name": st.stock_name,
                "total_score": float(s.total_score) if s.total_score else 0,
                "score_date": s.score_date,
                "reasons": (s.breakdown or {}).get("reasons", []),
            }
            for s, st in scores
        ]
    finally:
        db.close()


def _get_stock_score(stock_id: str) -> list[dict]:
    db = SessionLocal()
    try:
        since = date.today() - timedelta(days=7)
        rows = (
            db.query(DailyScore, Stock)
            .join(Stock, DailyScore.stock_id == Stock.stock_id)
            .filter(DailyScore.stock_id == stock_id, DailyScore.score_date >= since)
            .order_by(DailyScore.score_date.desc())
            .limit(7)
            .all()
        )
        return [
            {
                "score_date": s.score_date,
                "rank": s.rank,
                "total_score": float(s.total_score) if s.total_score else 0,
                "stock_name": st.stock_name,
                "tech_score": float(s.tech_score) if s.tech_score else 0,
                "inst_score": float(s.inst_score) if s.inst_score else 0,
                "margin_score": float(s.margin_score) if s.margin_score else 0,
                "macro_score": float(s.macro_score) if s.macro_score else 0,
                "reasons": (s.breakdown or {}).get("reasons", []),
            }
            for s, st in rows
        ]
    finally:
        db.close()


def _get_latest_macro() -> dict | None:
    db = SessionLocal()
    try:
        row = (
            db.query(MacroSnapshot)
            .order_by(MacroSnapshot.snapshot_date.desc())
            .first()
        )
        if not row:
            return None
        return {
            "snapshot_date": row.snapshot_date,
            "fed_cut_prob": float(row.fed_cut_prob) if row.fed_cut_prob else 0,
            "nvidia_beat_prob": float(row.nvidia_beat_prob) if row.nvidia_beat_prob else 0,
            "taiwan_strait_prob": float(row.taiwan_strait_prob) if row.taiwan_strait_prob else 0,
            "china_gdp_miss_prob": float(row.china_gdp_miss_prob) if row.china_gdp_miss_prob else 0,
            "oil_above_90_prob": float(row.oil_above_90_prob) if row.oil_above_90_prob else 0,
        }
    finally:
        db.close()


# ── Message builders ──────────────────────────────────────────────────────────

def _build_top_scores_flex(scores: list[dict]) -> dict:
    """Build top scores message with key selection reasons."""
    if not scores:
        return _text_msg("目前尚無評分資料，請稍後再試。")

    score_date = scores[0]["score_date"]
    lines = [f"📊 台股選股報告 ({score_date})\n"]
    for s in scores:
        bar = "█" * min(int(s["total_score"] / 10), 10)
        lines.append(f"#{s['rank']:02d} {s['stock_id']} {s['stock_name'] or ''}  {s['total_score']:.1f}分")
        lines.append(f"    {bar}")
        # Show up to 2 positive reasons (✅ only) as highlights
        positive = [r for r in s.get("reasons", []) if r.startswith("✅")][:2]
        for r in positive:
            lines.append(f"    {r}")
    lines.append("\n輸入股票代碼查詢個股完整分析")

    return _text_msg("\n".join(lines))


def _build_stock_detail(stock_id: str, rows: list[dict]) -> dict:
    if not rows:
        return _text_msg(f"找不到 {stock_id} 的評分資料（可能未在選股清單中）。")

    stock_name = rows[0]["stock_name"] or ""
    latest = rows[0]
    lines = [f"📈 {stock_id} {stock_name}\n"]

    # Latest day full breakdown
    lines.append(f"📅 最新評分 {latest['score_date']}  排名 #{latest['rank']}")
    lines.append(f"總分：{latest['total_score']:.1f}")
    lines.append(
        f"  技術 {latest['tech_score']:.0f}"
        f" ｜法人 {latest['inst_score']:.0f}"
        f" ｜籌碼 {latest['margin_score']:.0f}"
        f" ｜宏觀 {latest['macro_score']:.0f}"
    )

    reasons = latest.get("reasons", [])
    if reasons:
        lines.append("\n📌 選股原因：")
        for r in reasons:
            lines.append(f"  {r}")

    # Recent trend (skip latest, show rest)
    if len(rows) > 1:
        lines.append("\n📊 近期走勢：")
        for r in rows[1:]:
            trend = "▲" if r["total_score"] >= latest["total_score"] else "▼"
            lines.append(f"  {r['score_date']}  {r['total_score']:.1f}分 #{r['rank']} {trend}")

    return _text_msg("\n".join(lines))


def _build_macro_msg(macro: dict | None) -> dict:
    if not macro:
        return _text_msg("目前尚無宏觀信號資料。")

    d = macro
    lines = [
        f"🌍 宏觀信號快照 ({d['snapshot_date']})\n",
        f"Fed 降息機率：    {d['fed_cut_prob']:.1%}",
        f"Nvidia 財報達標：  {d['nvidia_beat_prob']:.1%}",
        f"台海風險：        {d['taiwan_strait_prob']:.1%}",
        f"中國 GDP 未達標：  {d['china_gdp_miss_prob']:.1%}",
        f"油價破 90 美元：   {d['oil_above_90_prob']:.1%}",
    ]
    return _text_msg("\n".join(lines))


def _build_help_msg() -> dict:
    text = (
        "🤖 台股選股機器人 使用說明\n\n"
        "📌 關鍵字指令：\n"
        "• 今日選股 → 今日 Top 10 選股\n"
        "• 宏觀 → Polymarket 宏觀信號\n"
        "• [股票代碼] → 個股評分（例：2330）\n"
        "• 立即評分 → 手動觸發選股評分\n"
        "• 說明 → 顯示此說明\n\n"
        "📌 快速按鈕可直接點選 👇"
    )
    return _text_msg(text)


# ── Main dispatch ─────────────────────────────────────────────────────────────

STOCK_CODE_RE = re.compile(r"^\d{4,6}$")

KEYWORD_MAP = {
    "今日選股": "top",
    "選股": "top",
    "top10": "top",
    "top": "top",
    "宏觀": "macro",
    "macro": "macro",
    "說明": "help",
    "help": "help",
    "?": "help",
    "？": "help",
    "立即評分": "trigger",
    "觸發選股": "trigger",
    "重新評分": "trigger",
}


def handle_text_message(reply_token: str, user_text: str) -> None:
    """Parse user text and reply accordingly."""
    text = user_text.strip()
    intent = KEYWORD_MAP.get(text.lower(), None)

    if intent == "trigger":
        _reply(reply_token, [_text_msg("⚙️ 開始執行評分，請稍候約 30 秒...", quick_reply=False)])
        try:
            from app.scheduler.tasks import run_scoring
            run_scoring()
        except Exception as e:
            logger.error(f"Manual trigger run_scoring error: {e}")
            _reply(reply_token, [_text_msg(f"❌ 評分執行失敗：{e}")])
            return
        scores = _get_today_top(10)
        msg = _build_top_scores_flex(scores)
        _reply(reply_token, [msg])
        return

    elif intent == "top":
        scores = _get_today_top(10)
        msg = _build_top_scores_flex(scores)

    elif intent == "macro":
        macro = _get_latest_macro()
        msg = _build_macro_msg(macro)

    elif intent == "help":
        msg = _build_help_msg()

    elif STOCK_CODE_RE.match(text):
        rows = _get_stock_score(text)
        msg = _build_stock_detail(text, rows)

    else:
        msg = _text_msg(
            f'不認識「{text}」，請輸入關鍵字或點選下方按鈕：'
        )

    _reply(reply_token, [msg])


def handle_postback(reply_token: str, data: str) -> None:
    """Handle postback events from buttons/menus."""
    handle_text_message(reply_token, data)
