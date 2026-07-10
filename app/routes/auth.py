"""Registration, login, current user."""
import re
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Workspace, Membership, MembershipRole, Category, StoreSettings
from app.schemas import RegisterRequest, LoginRequest, TokenResponse, UserResponse
from app.security import hash_password, verify_password, create_access_token
from app.deps import CurrentUser
from app.seed import DEFAULT_CATEGORIES, TAX_SYSTEMS

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Zа-яА-Я0-9]+", "-", text.strip().lower()).strip("-")
    return s or "workspace"


def _seed_workspace(db: Session, ws: Workspace) -> None:
    """Заполняет workspace дефолтными категориями и настройками."""
    for name, fby, fbs, note in DEFAULT_CATEGORIES:
        db.add(Category(workspace_id=ws.id, name=name, fby_rate=fby, fbs_rate=fbs, note=note))
    settings_obj = StoreSettings(
        workspace_id=ws.id,
        tax_system="УСН 6% (доходы)",
        tax_rate=TAX_SYSTEMS["УСН 6% (доходы)"],
    )
    db.add(settings_obj)


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter_by(email=req.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email уже зарегистрирован")

    user = User(email=req.email, password_hash=hash_password(req.password), name=req.name)
    db.add(user)
    db.flush()

    # Создаём workspace и делаем пользователя owner'ом
    base_slug = _slugify(req.workspace_name)
    slug = base_slug
    i = 1
    while db.query(Workspace).filter_by(slug=slug).first():
        i += 1
        slug = f"{base_slug}-{i}"

    ws = Workspace(name=req.workspace_name, slug=slug)
    db.add(ws)
    db.flush()
    db.add(Membership(user_id=user.id, workspace_id=ws.id, role=MembershipRole.OWNER))
    _seed_workspace(db, ws)

    db.commit()
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=req.email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный email или пароль")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Аккаунт заблокирован")
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser):
    return user
