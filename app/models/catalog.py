"""Каталог товаров и настройки магазина (по каждому workspace)."""
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Numeric, Float, Integer, Text, JSON, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Category(Base):
    """Категория товара и ставки комиссии Я.Маркета (FBY/FBS)."""
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("workspace_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    fby_rate: Mapped[float] = mapped_column(Float, default=0.15)
    fbs_rate: Mapped[float] = mapped_column(Float, default=0.22)
    note: Mapped[str] = mapped_column(String(300), default="")


class StoreSettings(Base):
    """Настройки магазина: система налогов, эквайринг, ДРР по умолчанию."""
    __tablename__ = "store_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True, index=True
    )
    tax_system: Mapped[str] = mapped_column(String(80), default="УСН 6% (доходы)")
    tax_rate: Mapped[float] = mapped_column(Float, default=0.06)
    payment_frequency: Mapped[str] = mapped_column(String(80), default="Еженедельно + 2 нед. отсрочка")
    acquiring_rate: Mapped[float] = mapped_column(Float, default=0.023)
    acquiring_manual_rate: Mapped[float] = mapped_column(Float, default=0.025)
    return_pct: Mapped[float] = mapped_column(Float, default=0.05)
    return_cost_rub: Mapped[float] = mapped_column(Float, default=200)
    default_drr_pct: Mapped[float] = mapped_column(Float, default=0.10)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Sku(Base):
    """Товар в каталоге workspace'а. sku — артикул продавца (offer_id для Ya.Market)."""
    __tablename__ = "skus"
    __table_args__ = (UniqueConstraint("workspace_id", "sku"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    sku: Mapped[str] = mapped_column(String(200), index=True)
    name: Mapped[str] = mapped_column(String(500), default="")
    category: Mapped[str] = mapped_column(String(200), default="Товары для дома (общ)")
    model: Mapped[str] = mapped_column(String(8), default="FBS")  # FBY | FBS

    length_cm: Mapped[float] = mapped_column(Float, default=0)
    width_cm: Mapped[float] = mapped_column(Float, default=0)
    height_cm: Mapped[float] = mapped_column(Float, default=0)
    weight_kg: Mapped[float] = mapped_column(Float, default=0)

    price_rub: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    cost_rub: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    drr_pct: Mapped[float | None] = mapped_column(Float, nullable=True)  # None → берётся из настроек

    # Дополнительные данные для истории (можно расширять)
    external_data: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
