"""Настройки магазина (store_settings) + справочники."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_workspace_for_user
from app.models import Workspace, StoreSettings
from app.schemas import StoreSettingsResponse, StoreSettingsUpdate
from app.seed import TAX_SYSTEMS, ACQUIRING_OPTIONS

router = APIRouter(prefix="/api/workspaces/{workspace_id}/settings", tags=["settings"])


@router.get("", response_model=StoreSettingsResponse)
def get_settings(
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    s = db.query(StoreSettings).filter_by(workspace_id=ws.id).first()
    if not s:
        s = StoreSettings(workspace_id=ws.id); db.add(s); db.commit(); db.refresh(s)
    return s


@router.patch("", response_model=StoreSettingsResponse)
def update_settings(
    req: StoreSettingsUpdate,
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    s = db.query(StoreSettings).filter_by(workspace_id=ws.id).first()
    if not s:
        s = StoreSettings(workspace_id=ws.id); db.add(s)
    data = req.model_dump(exclude_unset=True)
    # Если поменяли tax_system — обновим tax_rate из справочника
    if "tax_system" in data and "tax_rate" not in data:
        data["tax_rate"] = TAX_SYSTEMS.get(data["tax_system"], 0)
    # Если поменяли payment_frequency — обновим acquiring_rate из справочника
    if "payment_frequency" in data and "acquiring_rate" not in data:
        rate = ACQUIRING_OPTIONS.get(data["payment_frequency"])
        if rate is not None:
            data["acquiring_rate"] = rate
    for k, v in data.items():
        setattr(s, k, v)
    db.commit(); db.refresh(s)
    return s


@router.get("/tax-systems")
def list_tax_systems():
    return TAX_SYSTEMS


@router.get("/acquiring-options")
def list_acquiring_options():
    return ACQUIRING_OPTIONS
