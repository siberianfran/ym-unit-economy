"""Registration, login, current user, password reset."""
import re
import secrets
import hashlib
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models import (
    User, Workspace, Membership, MembershipRole,
    Category, StoreSettings, PasswordResetToken,
)
from app.schemas import (
    RegisterRequest, LoginRequest, TokenResponse, UserResponse,
    ForgotPasswordRequest, ResetPasswordRequest,
)
from app.security import hash_password, verify_password, create_access_token
from app.services.email import send_password_reset, EmailError
from app.deps import CurrentUser
from app.seed import DEFAULT_CATEGORIES, TAX_SYSTEMS

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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


# --------------------------- Password reset ---------------------------

@router.post("/forgot-password")
def forgot_password(
    req: ForgotPasswordRequest,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Отправляет письмо со ссылкой на сброс пароля.

    Всегда возвращает 200 (одинаковый ответ независимо от того, есть ли
    такой пользователь — чтобы не палить какие email зарегистрированы).
    """
    user = db.query(User).filter_by(email=req.email).first()
    if user and user.is_active:
        # Инвалидируем старые неиспользованные токены
        db.query(PasswordResetToken).filter(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        ).delete()

        raw_token = secrets.token_urlsafe(32)
        prt = PasswordResetToken(
            user_id=user.id,
            token_hash=_hash_token(raw_token),
            expires_at=datetime.utcnow() + timedelta(
                minutes=settings.password_reset_expire_minutes
            ),
        )
        db.add(prt)
        db.commit()

        reset_url = f"{settings.app_url.rstrip('/')}/?reset_token={raw_token}"

        # Отправляем в фоне чтобы не блокировать response и не палить успех/неуспех
        def _send_safely():
            try:
                send_password_reset(user.email, reset_url)
            except EmailError as e:
                # Логируем, но не показываем клиенту
                print(f"[email] Failed to send password reset to {user.email}: {e}")

        bg.add_task(_send_safely)

    return {"status": "ok", "message": "Если email зарегистрирован — письмо отправлено"}


@router.post("/reset-password", response_model=TokenResponse)
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Устанавливает новый пароль по токену. Возвращает access_token — сразу залогинен."""
    token_hash = _hash_token(req.token)
    prt = db.query(PasswordResetToken).filter_by(token_hash=token_hash).first()
    if not prt:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ссылка недействительна")
    if prt.used_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ссылка уже использована")
    if prt.expires_at < datetime.utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ссылка истекла — запроси новую")

    user = db.query(User).filter_by(id=prt.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Аккаунт недоступен")

    user.password_hash = hash_password(req.password)
    prt.used_at = datetime.utcnow()
    db.commit()

    return TokenResponse(access_token=create_access_token(user.id))
