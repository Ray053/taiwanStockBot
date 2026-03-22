"""add market signal columns to macro_snapshots

Revision ID: 002
Revises: 001
Create Date: 2026-03-22 00:00:00.000000

New columns:
  txf_night_change  — Taiwan futures night session % change (proxy via EWT ETF)
  sox_change        — Philadelphia Semiconductor Index daily % change
  nasdaq_change     — NASDAQ Composite daily % change
  sp500_change      — S&P 500 daily % change
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("macro_snapshots", sa.Column("txf_night_change", sa.Numeric(6, 4), nullable=True))
    op.add_column("macro_snapshots", sa.Column("sox_change", sa.Numeric(6, 4), nullable=True))
    op.add_column("macro_snapshots", sa.Column("nasdaq_change", sa.Numeric(6, 4), nullable=True))
    op.add_column("macro_snapshots", sa.Column("sp500_change", sa.Numeric(6, 4), nullable=True))


def downgrade() -> None:
    op.drop_column("macro_snapshots", "sp500_change")
    op.drop_column("macro_snapshots", "nasdaq_change")
    op.drop_column("macro_snapshots", "sox_change")
    op.drop_column("macro_snapshots", "txf_night_change")
