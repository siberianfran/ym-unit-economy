"""Модели финансовых отчётов (P&L по маркетплейсам)."""
from datetime import datetime, date
from sqlalchemy import String, DateTime, Date, ForeignKey, Numeric, Float, Integer, Text, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class FinReport(Base):
    __tablename__ = "fin_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    mp_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("marketplace_accounts.id", ondelete="SET NULL"), nullable=True
    )
    marketplace: Mapped[str] = mapped_column(String(20), default="ya_market")
    period_from: Mapped[date] = mapped_column(Date, index=True)
    period_to: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(30), default="key_indicators")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    ya_report_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    periods: Mapped[list["FinReportPeriod"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class FinReportPeriod(Base):
    __tablename__ = "fin_report_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("fin_reports.id", ondelete="CASCADE"), index=True
    )
    period_type: Mapped[str] = mapped_column(String(10), default="week")
    period_from: Mapped[date] = mapped_column(Date)
    period_to: Mapped[date] = mapped_column(Date)

    revenue_gross: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    revenue_return: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    revenue_correction: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    revenue_total: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    revenue_without_spp: Mapped[float] = mapped_column(Numeric(14, 2), default=0)

    commission: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    delivery_logistics: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    logistics_correction: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    logistics_total: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    storage: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    processing: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    penalties: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    advertising: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    acquiring: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    other: Mapped[float] = mapped_column(Numeric(14, 2), default=0)

    payout: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    cost_of_sales: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    profit: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    margin_pct: Mapped[float] = mapped_column(Float, default=0)
    units_sold: Mapped[int] = mapped_column(Integer, default=0)

    report: Mapped["FinReport"] = relationship(back_populates="periods")


class CostSnapshot(Base):
    __tablename__ = "cost_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column(
        ForeignKey("skus.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    cost_rub: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    effective_from: Mapped[date] = mapped_column(Date, index=True)
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

