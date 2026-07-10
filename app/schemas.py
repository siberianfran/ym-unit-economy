"""Pydantic schemas for API I/O."""
from pydantic import BaseModel, EmailStr, Field, ConfigDict


# ---- Auth ----
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    name: str = ""
    workspace_name: str = "Мой магазин"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    name: str


# ---- Workspaces ----
class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    slug: str
    role: str = "member"


# ---- Store settings ----
class StoreSettingsUpdate(BaseModel):
    tax_system: str | None = None
    tax_rate: float | None = None
    payment_frequency: str | None = None
    acquiring_rate: float | None = None
    acquiring_manual_rate: float | None = None
    return_pct: float | None = None
    return_cost_rub: float | None = None
    default_drr_pct: float | None = None


class StoreSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    tax_system: str
    tax_rate: float
    payment_frequency: str
    acquiring_rate: float
    acquiring_manual_rate: float
    return_pct: float
    return_cost_rub: float
    default_drr_pct: float


# ---- Categories ----
class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    fby_rate: float = 0.15
    fbs_rate: float = 0.22
    note: str = ""


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    fby_rate: float
    fbs_rate: float
    note: str


# ---- SKU ----
class SkuBase(BaseModel):
    sku: str
    name: str = ""
    category: str = "Товары для дома (общ)"
    model: str = "FBS"
    length_cm: float = 0
    width_cm: float = 0
    height_cm: float = 0
    weight_kg: float = 0
    price_rub: float = 0
    cost_rub: float = 0
    drr_pct: float | None = None


class SkuCreate(SkuBase):
    pass


class SkuUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    model: str | None = None
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    price_rub: float | None = None
    cost_rub: float | None = None
    drr_pct: float | None = None


class SkuResponse(SkuBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# ---- Marketplace account ----
class MarketplaceAccountCreate(BaseModel):
    marketplace: str = "ya_market"
    api_token: str
    business_id: int | None = None
    campaign_id: int | None = None
    label: str = ""


class MarketplaceAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    marketplace: str
    business_id: int | None
    campaign_id: int | None
    label: str
    # api_token НЕ отдаём — секрет


# ---- Calc ----
class CalcRequest(BaseModel):
    sku_ids: list[int] | None = None  # если None — считаем все SKU в workspace
    tax_system: str | None = None
    acquiring_rate: float | None = None
    drr_pct: float | None = None
