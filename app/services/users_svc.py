from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User

COOKIE = "cairn_user"
DEFAULT_EMAIL = "s.chen@bank.example"


def current_user(db: Session, request: Request) -> User:
    raw = request.cookies.get(COOKIE, "")
    if raw.isdigit():
        u = db.get(User, int(raw))
        if u:
            return u
    return db.scalar(select(User).where(User.email == DEFAULT_EMAIL)) or db.scalar(select(User).order_by(User.id))
