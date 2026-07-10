"""Управление токенами маркетплейсов (Ya.Market API)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_workspace_for_user
from app.models import Workspace, MarketplaceAccount
from app.schemas import MarketplaceAccountCreate, MarketplaceAccountResponse

router = APIRouter(prefix="/api/workspaces/{workspace_id}/marketplace-accounts", tags=["marketplace"])


@router.get("", response_model=list[MarketplaceAccountResponse])
def list_accounts(
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    return db.query(MarketplaceAccount).filter_by(workspace_id=ws.id).all()


@router.post("", response_model=MarketplaceAccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    req: MarketplaceAccountCreate,
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    acc = MarketplaceAccount(workspace_id=ws.id, **req.model_dump())
    db.add(acc); db.commit(); db.refresh(acc)
    return acc


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    account_id: int,
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    acc = db.query(MarketplaceAccount).filter_by(workspace_id=ws.id, id=account_id).first()
    if not acc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.delete(acc); db.commit()
