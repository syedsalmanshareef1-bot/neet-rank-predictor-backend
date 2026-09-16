"""
Creates (or resets the password of) an admin user.

Usage:
    python scripts/create_admin.py --username admin --password "SomeStrongPassword123!"

If --username/--password are omitted, falls back to FIRST_ADMIN_USERNAME /
FIRST_ADMIN_PASSWORD from the environment (see .env.example).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.database import SessionLocal
from app.models import AdminUser
from app.security import hash_password


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--role", default="admin")
    args = parser.parse_args()

    settings = get_settings()
    username = args.username or settings.FIRST_ADMIN_USERNAME
    password = args.password or settings.FIRST_ADMIN_PASSWORD

    if not username or not password:
        print("Username and password are required (via args or .env).", file=sys.stderr)
        sys.exit(1)
    if password == "change-this-password":
        print("Refusing to use the default placeholder password — set a real one.", file=sys.stderr)
        sys.exit(1)

    db = SessionLocal()
    try:
        user = db.query(AdminUser).filter(AdminUser.username == username).one_or_none()
        if user:
            user.hashed_password = hash_password(password)
            user.is_active = True
            print(f"Updated password for existing admin '{username}'.")
        else:
            user = AdminUser(username=username, hashed_password=hash_password(password), role=args.role)
            db.add(user)
            print(f"Created admin '{username}'.")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
