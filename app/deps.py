"""FastAPI dependencies: current user, current workspace."""
from typing import Annotated
from fastapi import Depends, HTTPException, status, Header, Path
from sqlalchemy.orm import Session
from app.database import get_db
from app.security import decode_token
from app.models import User, Workspace, Membership


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> User:
    """Extract user from Bearer token."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Missing or invalid Authorization header",
            {"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1]
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_workspace_for_user(
    workspace_id: int,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> Workspace:
    """Проверяет что user состоит в workspace, возвращает Workspace."""
    ws = db.get(Workspace, workspace_id)
    if not ws:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found")
    membership = (
        db.query(Membership)
        .filter_by(user_id=user.id, workspace_id=workspace_id)
        .first()
    )
    if not membership:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this workspace")
    return ws
