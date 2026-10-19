"""Authorization: who may see/edit which project, and which projects feed a user's learning/retrieval pool.

Every API route except auth/health runs `authz_guard`, which resolves any id in the path to its project and
checks access (404 when invisible, so ids cannot be probed; 403 for writes by viewers). List endpoints filter
with `visible_project_ids`. Learning, retrieval and backtests use `pool_project_ids`."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.auth import SAFE_METHODS, Forbidden, current_user
from app.core.errors import NotFound
from app.db.models import (
    AgentOperation,
    AgentSession,
    BacktestRun,
    ChangeProposal,
    ClarifyingQuestion,
    Document,
    Estimate,
    Job,
    LearnedRule,
    Module,
    Project,
    ProjectMember,
    ProjectMemory,
    Setting,
    Task,
    UnplannedActual,
    User,
)
from app.db.session import get_db

ARCHIVE_SETTING = "workspace"


def include_archive_for_all(db: Session) -> bool:
    row = db.get(Setting, ARCHIVE_SETTING)
    return bool((row.value or {}).get("include_archive_for_all")) if row else False


def is_admin(user: User) -> bool:
    return user.role == "admin"


def visible_project_ids(db: Session, user: User) -> list[uuid.UUID] | None:
    """None = everything (admin)."""
    if is_admin(user):
        return None
    shared = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
    return list(db.scalars(select(Project.id).where(or_(Project.owner_id == user.id, Project.id.in_(shared)))))


def pool_project_ids(db: Session, user_id: uuid.UUID | None) -> list[uuid.UUID] | None:
    """Projects whose history may calibrate / be retrieved for this user. None = everything (admin)."""
    user = db.get(User, user_id) if user_id else None
    if user is None or is_admin(user):
        return None
    shared = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
    conds = [Project.owner_id == user.id, Project.id.in_(shared),
             (Project.shared_to_workspace.is_(True)) & (Project.is_archive.is_(False))]
    if include_archive_for_all(db):
        conds.append(Project.is_archive.is_(True))
    return list(db.scalars(select(Project.id).where(or_(*conds))))


def pool_uses_archive(db: Session, user_id: uuid.UUID | None) -> bool:
    user = db.get(User, user_id) if user_id else None
    return bool(user and not is_admin(user) and include_archive_for_all(db))


def project_role(db: Session, user: User, project_id: uuid.UUID) -> str | None:
    """'owner' | 'editor' | 'viewer' | None."""
    p = db.get(Project, project_id)
    if p is None:
        return None
    if is_admin(user) or p.owner_id == user.id:
        return "owner"
    m = db.scalar(select(ProjectMember.role).where(ProjectMember.project_id == project_id,
                                                   ProjectMember.user_id == user.id))
    return m


def check_project(db: Session, user: User, project_id: uuid.UUID | None, write: bool) -> str:
    role = project_role(db, user, project_id) if project_id else None
    if role is None:
        raise NotFound("Resource")
    if write and role == "viewer":
        raise Forbidden("You have view-only access to this project")
    return role


def _est(db: Session, eid: uuid.UUID | None) -> uuid.UUID | None:
    e = db.get(Estimate, eid) if eid else None
    return e.project_id if e else None


def _attr(model, attr: str, then: Callable | None = None):
    def resolve(db: Session, id_: uuid.UUID) -> uuid.UUID | None:
        obj = db.get(model, id_)
        if obj is None:
            return None
        v = getattr(obj, attr)
        return then(db, v) if then else v
    return resolve


def _batch(db: Session, bid: uuid.UUID) -> uuid.UUID | None:
    op = db.scalar(select(AgentOperation).where(AgentOperation.batch_id == bid).limit(1))
    return _est(db, op.estimate_id) if op else None


PROJECT_RESOLVERS: dict[str, Callable[[Session, uuid.UUID], uuid.UUID | None]] = {
    "project_id": lambda db, i: i if db.get(Project, i) else None,
    "estimate_id": _est,
    "task_id": _attr(Task, "estimate_id", _est),
    "module_id": _attr(Module, "estimate_id", _est),
    "document_id": _attr(Document, "project_id"),
    "session_id": _attr(AgentSession, "estimate_id", _est),
    "batch_id": _batch,
    "memory_id": _attr(ProjectMemory, "project_id"),
    "unplanned_id": _attr(UnplannedActual, "project_id"),
    "proposal_id": _attr(ChangeProposal, "estimate_id", _est),
    "question_id": _attr(ClarifyingQuestion, "estimate_id", _est),
}


def _owned(model, attr: str) -> Callable[[Session, User, uuid.UUID], None]:
    def check(db: Session, user: User, id_: uuid.UUID) -> None:
        obj = db.get(model, id_)
        if obj is None or (not is_admin(user) and getattr(obj, attr) != user.id):
            raise NotFound("Resource")
    return check


OWNED: dict[str, Callable[[Session, User, uuid.UUID], None]] = {
    "job_id": _owned(Job, "user_id"),
    "run_id": _owned(BacktestRun, "owner_id"),
    "rule_id": _owned(LearnedRule, "owner_id"),
}

ADMIN_ONLY_PARAMS = {"role_id", "category_id"}


def authz_guard(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
    pp = request.path_params
    write = request.method not in SAFE_METHODS
    for name, raw in pp.items():
        if name == "member_user_id":
            continue  # owner-only handlers check this
        if name == "op_id" and "proposal_id" in pp:
            continue  # proposal op ids are strings inside the proposal; the proposal check covers them
        if name in ADMIN_ONLY_PARAMS:
            if write and not is_admin(user):
                raise Forbidden("Only an admin can change workspace reference data")
            continue
        try:
            id_ = uuid.UUID(str(raw))
        except ValueError:
            raise NotFound("Resource") from None
        if name == "op_id":
            check_project(db, user, _attr(AgentOperation, "estimate_id", _est)(db, id_), write)
        elif name in PROJECT_RESOLVERS:
            check_project(db, user, PROJECT_RESOLVERS[name](db, id_), write)
        elif name in OWNED:
            OWNED[name](db, user, id_)
    return user
