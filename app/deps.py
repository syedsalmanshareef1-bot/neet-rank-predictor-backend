from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/admin/auth/login", auto_error=False)


def get_current_admin(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.AdminUser:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate admin credentials",
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
