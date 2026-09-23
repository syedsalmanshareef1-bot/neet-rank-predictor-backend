from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.AdminUser:
    """Any signed-in account, regardless of role — used to gate the
    predictor and reference-data endpoints behind login."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        raise credentials_exception

    user = db.query(models.AdminUser).filter(models.AdminUser.username == payload["sub"]).one_or_none()
    if not user or not user.is_active:
        raise credentials_exception
    return user


def get_current_admin(
    user: models.AdminUser = Depends(get_current_user),
) -> models.AdminUser:
    """A signed-in account that specifically has the admin role — used to
    gate the import/master-data endpoints. Builds on get_current_user, so
    the token/expiry checks only live in one place."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires an admin account.",
        )
    return user