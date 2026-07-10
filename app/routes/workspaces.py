"""Список workspaces пользователя, создание новых."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import CurrentUser
from app.models import Workspace, Membership, MembershipRole, Category, StoreSettings
from app.schemas import WorkspaceCreate, WorkspaceResponse
from app.seed import DEFAULT_CATEGORIES, TAX_SYSTEMS
import re

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Zа-яА-Я0-9]+", "-", text.strip().lower()).strip("-")
    return s or "workspace"


@router.get("", response_model=list[WorkspaceResponse])
def my_workspaces(user: CurrentUser, db: Session = Depends(get_db)):
    """Все workspaces, где я состою."""
    memberships = db.query(Membership).filter_by(user_id=user.id).all()
    result = []
    for m in memberships:
        w = m.workspace
        result.append(WorkspaceResponse(
            id=w.id, name=w.name, slug=w.slug, role=m.role.value,
        ))
    return result


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
def create_workspace(req: WorkspaceCreate, user: CurrentUser, db: Session = Depends(get_db)):
    """Создать новый workspace (я стану owner'ом)."""
    base_slug = _slugify(req.name)
    slug = base_slug
    i = 1
    while db.query(Workspace).filter_by(slug=slug).first():
        i += 1
        slug = f"{base_slug}-{i}"

    ws = Workspace(name=req.name, slug=slug)
    db.add(ws)
    db.flush()
    m = Membership(user_id=user.id, workspace_id=ws.id, role=MembershipRole.OWNER)
    db.add(m)
    # Дефолтные категории и настройки
    for name, fby, fbs, note in DEFAULT_CATEGORIES:
        db.add(Category(workspace_id=ws.id, name=name, fby_rate=fby, fbs_rate=fbs, note=note))
    db.add(StoreSettings(workspace_id=ws.id, tax_system="УСН 6% (доходы)", tax_rate=TAX_SYSTEMS["УСН 6% (доходы)"]))
    db.commit()

    return WorkspaceResponse(id=ws.id, name=ws.name, slug=ws.slug, role="owner")
