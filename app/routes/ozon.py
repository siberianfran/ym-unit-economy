"""Endpoints Ozon: юнит-экономика (любая категория), импорт отчётов, real-time синк.

Модель — по образцу ya_market: per-workspace, авторизация через workspace.
Логика расчёта — пакет app.services.ozon_core (протестированный движок Ozon).
"""
import os
import tempfile
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_workspace_for_user
from app.models import Workspace, MarketplaceAccount
from app.models.catalog import StoreSettings

from app.services.ozon_core.ozon_unit import calc_single_sku_ozon, load_settings
from app.services.ozon_core import ozon_full_report, ozon_import, ozon_commission_catalog
from app.services.ozon_core.ozon_api import OzonSellerAPI, normalize_transactions, OzonAPIError

router = APIRouter(prefix="/api/workspaces/{workspace_id}/ozon", tags=["ozon"])


def _store_overrides(db: Session, ws_id: int) -> dict:
    ss = db.query(StoreSettings).filter_by(workspace_id=ws_id).first()
    if not ss:
        return {}
    ov = {
        "tax_system": ss.tax_system,
        "acquiring_rate": ss.acquiring_rate,
        "drr_pct": ss.default_drr_pct,
        "returns_pct": ss.return_pct,
        "nonlocal_surcharge_pct": getattr(ss, "ozon_nonlocal_pct", 0.0) or 0.0,
    }
    if getattr(ss, "ozon_commission_override", None):
        ov["commission_override"] = ss.ozon_commission_override
    return ov


@router.get("/categories")
def ozon_categories(ws: Workspace = Depends(get_workspace_for_user)):
    s = load_settings()
    cat = s.get("commission_catalog") or {}
    return {"count": len(cat), "categories": sorted(cat.keys())}


@router.get("/category-types")
def ozon_category_types(category: str, ws: Workspace = Depends(get_workspace_for_user)):
    s = load_settings()
    cat = (s.get("commission_catalog") or {}).get(category, {})
    return {"category": category, "types": sorted(k for k in cat if k != "_default")}


@router.post("/calc")
def ozon_calc(payload: dict,
              ws: Workspace = Depends(get_workspace_for_user),
              db: Session = Depends(get_db)):
    ov = _store_overrides(db, ws.id)
    body = {k: v for k, v in payload.items() if v is not None}
    args = {**ov, **body}
    try:
        return calc_single_sku_ozon(**args)
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Ошибка расчёта: {e}")


def _save_tmp(f: UploadFile) -> str:
    fd, path = tempfile.mkstemp(suffix="_" + (f.filename or "up.xlsx"))
    with os.fdopen(fd, "wb") as out:
        out.write(f.file.read())
    return path


@router.post("/import-report")
def ozon_import_report(report: UploadFile = File(...), cost: UploadFile = File(None),
                       ws: Workspace = Depends(get_workspace_for_user)):
    rp = _save_tmp(report)
    try:
        if cost is not None:
            cp = _save_tmp(cost)
            out = os.path.join(tempfile.gettempdir(), f"marja_pnl_{ws.id}.xlsx")
            return ozon_full_report.build(rp, cp, out)
        return ozon_import.import_nachisleniya(rp)
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Ошибка импорта: {e}")


@router.post("/import-commission-catalog")
def ozon_import_catalog(file: UploadFile = File(...),
                        ws: Workspace = Depends(get_workspace_for_user)):
    p = _save_tmp(file)
    try:
        return ozon_commission_catalog.import_catalog(p)
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Ошибка каталога: {e}")


@router.post("/sync")
def ozon_sync(payload: dict,
              ws: Workspace = Depends(get_workspace_for_user),
              db: Session = Depends(get_db)):
    acc = db.query(MarketplaceAccount).filter_by(workspace_id=ws.id, marketplace="ozon").first()
    if not acc or not acc.api_token or not acc.business_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Нет подключённого Ozon-аккаунта (Client-Id -> business_id, Api-Key -> api_token).")
    api = OzonSellerAPI(str(acc.business_id), acc.api_token)
    try:
        ops = api.finance_transactions(payload["date_from"], payload["date_to"])
        return normalize_transactions(ops)
    except OzonAPIError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e))
