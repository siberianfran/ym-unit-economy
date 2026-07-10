"""Marketplace API credentials per workspace."""
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, func, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class MarketplaceAccount(Base):
    __tablename__ = "marketplace_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    marketplace: Mapped[str] = mapped_column(String(32), default="ya_market")  # ya_market | ozon | wb
    api_token: Mapped[str] = mapped_column(Text)  # OAuth-токен или API-ключ Partner API
    business_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # ID кабинета (для Ya.Market — businessId)
    campaign_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # ID магазина внутри бизнеса
    label: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
