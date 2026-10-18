import uuid

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db


def current_user_id(x_user_id: str | None = Header(default=None), db: Session = Depends(get_db)) -> uuid.UUID | None:
    """Demo-only identity: the frontend sends X-User-Id from the user switcher. Unknown ids are ignored."""
    if x_user_id:
        try:
            uid = uuid.UUID(x_user_id)
        except ValueError:
            uid = None
        if uid and db.get(User, uid):
            return uid
    return db.scalar(select(User.id).where(User.role == "pm").order_by(User.email))
