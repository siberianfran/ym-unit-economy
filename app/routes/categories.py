"""CRUD категорий по workspace."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import CurrentUser, get_workspace_for_user
from app.models import Category, Workspace
from app.schemas import CategoryCreate, CategoryResponse

router = APIRouter(prefix="/api/workspaces/{workspace_id}/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
def list_categories(
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    return db.query(Category).filter_by(workspace_id=ws.id).order_by(Category.name).all()


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def upsert_category(
    req: CategoryCreate,
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    existing = db.query(Category).filter_by(workspace_id=ws.id, name=req.name).first()
    if existing:
        existing.fby_rate = req.fby_rate
        existing.fbs_rate = req.fbs_rate
        existing.note = req.note
    else:
        existing = Category(workspace_id=ws.id, name=req.name,
                            fby_rate=req.fby_rate, fbs_rate=req.fbs_rate, note=req.note)
        db.add(existing)
    db.commit()
    db.refresh(existing)
    return existing


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    name: str,
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    cat = db.query(Category).filter_by(workspace_id=ws.id, name=name).first()
    if not cat:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    db.delete(cat); db.commit()
    return None
