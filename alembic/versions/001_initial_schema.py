"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # stocks
    op.create_table(
        "stocks",
        sa.Column("stock_id", sa.String(10), primary_key=True),
        sa.Column("stock_name", sa.String(50), nullable=False),
        sa.Column("sector", sa.String(30), nullable=True),
        sa.Column("market", sa.String(10), server_default="TWSE"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )

    # daily_kline
    op.create_table(
        "daily_kline",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("stock_id", sa.String(10), sa.ForeignKey("stocks.stock_id"), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(10, 2)),
        sa.Column("high", sa.Numeric(10, 2)),
        sa.Column("low", sa.Numeric(10, 2)),
        sa.Column("close", sa.Numeric(10, 2)),
        sa.Column("volume", sa.BigInteger()),
        sa.Column("ma5", sa.Numeric(10, 2)),
        sa.Column("ma20", sa.Numeric(10, 2)),
        sa.Column("ma60", sa.Numeric(10, 2)),
        sa.Column("rsi14", sa.Numeric(6, 2)),
        sa.Column("macd", sa.Numeric(10, 4)),
        sa.Column("macd_signal", sa.Numeric(10, 4)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("stock_id", "trade_date", name="uq_kline_stock_date"),
    )
    op.create_index("idx_kline_date", "daily_kline", ["trade_date"])
    op.create_index("idx_kline_stock", "daily_kline", ["stock_id", "trade_date"])

    # institutional_investors
    op.create_table(
        "institutional_investors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("stock_id", sa.String(10), sa.ForeignKey("stocks.stock_id"), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("foreign_net", sa.BigInteger()),
        sa.Column("trust_net", sa.BigInteger()),
        sa.Column("dealer_net", sa.BigInteger()),
        sa.Column("total_net", sa.BigInteger()),
        sa.UniqueConstraint("stock_id", "trade_date", name="uq_inst_stock_date"),
    )
    op.create_index("idx_inst_stock", "institutional_investors", ["stock_id", "trade_date"])

    # margin_trading
    op.create_table(
        "margin_trading",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("stock_id", sa.String(10), sa.ForeignKey("stocks.stock_id"), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("margin_balance", sa.BigInteger()),
        sa.Column("margin_change", sa.BigInteger()),
        sa.Column("short_balance", sa.BigInteger()),
        sa.Column("short_change", sa.BigInteger()),
        sa.UniqueConstraint("stock_id", "trade_date", name="uq_margin_stock_date"),
    )

    # macro_snapshots
    op.create_table(
        "macro_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_date", sa.Date(), nullable=False, unique=True),
        sa.Column("fed_cut_prob", sa.Numeric(5, 4)),
        sa.Column("nvidia_beat_prob", sa.Numeric(5, 4)),
        sa.Column("taiwan_strait_prob", sa.Numeric(5, 4)),
        sa.Column("china_gdp_miss_prob", sa.Numeric(5, 4)),
        sa.Column("oil_above_90_prob", sa.Numeric(5, 4)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )

    # daily_scores
    op.create_table(
        "daily_scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("score_date", sa.Date(), nullable=False),
        sa.Column("stock_id", sa.String(10), sa.ForeignKey("stocks.stock_id"), nullable=False),
        sa.Column("total_score", sa.Numeric(6, 2)),
        sa.Column("tech_score", sa.Numeric(6, 2)),
        sa.Column("inst_score", sa.Numeric(6, 2)),
        sa.Column("margin_score", sa.Numeric(6, 2)),
        sa.Column("macro_score", sa.Numeric(6, 2)),
        sa.Column("rank", sa.Integer()),
        sa.Column("breakdown", JSONB()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("score_date", "stock_id", name="uq_score_date_stock"),
    )
    op.create_index("idx_scores_date", "daily_scores", ["score_date", "total_score"])


def downgrade() -> None:
    op.drop_index("idx_scores_date", table_name="daily_scores")
    op.drop_table("daily_scores")
    op.drop_table("macro_snapshots")
    op.drop_table("margin_trading")
    op.drop_index("idx_inst_stock", table_name="institutional_investors")
    op.drop_table("institutional_investors")
    op.drop_index("idx_kline_stock", table_name="daily_kline")
    op.drop_index("idx_kline_date", table_name="daily_kline")
    op.drop_table("daily_kline")
    op.drop_table("stocks")
