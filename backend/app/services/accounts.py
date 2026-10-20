"""Removal of throw-away guest accounts (quick sign-in) and everything they own."""

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.base import Base
from app.db.models import Project, User

GUEST_DOMAIN = "@guest.calibr"


def is_purgeable_guest(user: User) -> bool:
    return (user.role == "member" and not user.archived
            and (user.email or "").lower().endswith(GUEST_DOMAIN))


def purge_guest(db: Session, user: User) -> dict[str, int]:
    """Deletes a guest member, the projects they own, their sessions and their references. Never touches admins,
    archived users or archived projects."""
    if not is_purgeable_guest(user):
        raise AppError("not_deletable", "Only guest accounts can be deleted", 403)
    owned = db.query(Project).filter(Project.owner_id == user.id).all()
    if any(p.is_archive for p in owned):
        raise AppError("archived", "Archived reference projects cannot be deleted", 409)
    for p in owned:
        db.delete(p)
    db.flush()
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            if any(fk.column.table.name == "users" for fk in col.foreign_keys):
                if col.nullable:
                    db.execute(update(table).where(col == user.id).values({col.name: None}))
                else:
                    db.execute(delete(table).where(col == user.id))
    db.delete(user)
    db.commit()
    return {"projects": len(owned), "users": 1}
