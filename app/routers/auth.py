from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.deps import get_current_user
from app.schemas import LoginRequest, RegisterRequest, Token, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    """Public self-registration. Always creates a regular ("user") account —
    admin accounts are only ever created via scripts/create_admin.py, never
    through this public endpoint, so nobody can grant themselves admin
    access by signing up."""
    existing = db.query(models.AdminUser).filter(models.AdminUser.username == payload.username).one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That username is already taken.")

    user = models.AdminUser(
        username=payload.username,
        hashed_password=hash_password(payload.password),
        role="user",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(subject=user.username, role=user.role)
    return Token(access_token=token)


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """General login for any account (user or admin) — the same check the
    Admin Dashboard's own login already performed, just under a public
    /auth/login path instead of /admin/auth/login, and taking JSON instead
    of a form body since this is what the site-wide login page sends."""
    user = db.query(models.AdminUser).filter(models.AdminUser.username == payload.username).one_or_none()
    if not user or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    token = create_access_token(subject=user.username, role=user.role)
    return Token(access_token=token)


@router.get("/me", response_model=UserOut)
def read_current_user(user: models.AdminUser = Depends(get_current_user)):
    return UserOut(username=user.username, role=user.role)
