import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access import check_project, is_admin, project_role, visible_project_ids
from app.core.auth import Forbidden, current_user
from app.core.errors import AppError, NotFound
from app.core.usage import AIRateLimit
from app.db.models import Document, DocumentChunk, Project, ProjectMember, User
from app.db.session import get_db
from app.schemas import api as S
from app.services import documents as docs
from app.services.views import project_list

router = APIRouter(tags=["projects"])


class ShareIn(BaseModel):
    email: EmailStr
    role: Literal["viewer", "editor"] = "viewer"


def _out(db: Session, p: Project, user: User) -> S.ProjectOut:
    o = S.ProjectOut.model_validate(p)
    o.access = project_role(db, user, p.id)
    o.tech_tags = [t for t in o.tech_tags if t != "demo-data"]
    return o


def _owner_only(db: Session, user: User, project_id: uuid.UUID) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise NotFound("Project")
    if not (is_admin(user) or p.owner_id == user.id):
        raise Forbidden("Only the project owner can do this")
    return p


@router.get("/projects", response_model=list[S.ProjectListItem])
def list_projects(status: str | None = None, search: str | None = None, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    items = project_list(db, status, search, visible_project_ids(db, user))
    for it in items:
        it.tech_tags = [t for t in it.tech_tags if t != "demo-data"]
    return items


@router.post("/projects", response_model=S.ProjectOut, status_code=201)
def create_project(body: S.ProjectIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = Project(**body.model_dump(), status="draft", data_source="user", created_by=user.id, owner_id=user.id)
    db.add(p)
    db.commit()
    return _out(db, p, user)


@router.get("/projects/{project_id}", response_model=S.ProjectOut)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = db.get(Project, project_id)
    if p is None:
        raise NotFound("Project")
    return _out(db, p, user)


@router.patch("/projects/{project_id}", response_model=S.ProjectOut)
def patch_project(project_id: uuid.UUID, body: S.ProjectPatch, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    p = db.get(Project, project_id)
    if p is None:
        raise NotFound("Project")
    data = body.model_dump(exclude_unset=True)
    if "shared_to_workspace" in data:
        _owner_only(db, user, project_id)
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    return _out(db, p, user)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    p = _owner_only(db, user, project_id)
    if p.is_archive:
        raise AppError("archived", "Archived reference projects cannot be deleted", 409)
    db.delete(p)
    db.commit()


# ---------- sharing ----------
@router.get("/projects/{project_id}/members")
def list_members(project_id: uuid.UUID, db: Session = Depends(get_db)) -> list[dict]:
    p = db.get(Project, project_id)
    owner = db.get(User, p.owner_id) if p and p.owner_id else None
    rows = db.execute(select(ProjectMember, User).join(User, User.id == ProjectMember.user_id)
                      .where(ProjectMember.project_id == project_id).order_by(User.name))
    out = [{"user_id": str(owner.id), "name": owner.name, "email": owner.email, "role": "owner"}] if owner else []
    return out + [{"user_id": str(u.id), "name": u.name, "email": u.email, "role": m.role} for m, u in rows]


@router.post("/projects/{project_id}/members", status_code=201)
def add_member(project_id: uuid.UUID, body: ShareIn, db: Session = Depends(get_db),
               user: User = Depends(current_user)) -> dict:
    p = _owner_only(db, user, project_id)
    target = db.scalar(select(User).where(func.lower(User.email) == body.email.lower(), User.is_active.is_(True),
                                          User.archived.is_(False)))
    if target is None:
        raise AppError("user_not_found", "No active account uses that email. Ask them to sign up first.", 404)
    if target.id == p.owner_id:
        raise AppError("already_owner", "That person already owns the project", 409)
    m = db.scalar(select(ProjectMember).where(ProjectMember.project_id == p.id, ProjectMember.user_id == target.id))
    if m is None:
        db.add(ProjectMember(project_id=p.id, user_id=target.id, role=body.role))
    else:
        m.role = body.role
    db.commit()
    return {"user_id": str(target.id), "name": target.name, "email": target.email, "role": body.role}


@router.delete("/projects/{project_id}/members/{member_user_id}", status_code=204)
def remove_member(project_id: uuid.UUID, member_user_id: uuid.UUID, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    _owner_only(db, user, project_id)
    m = db.scalar(select(ProjectMember).where(ProjectMember.project_id == project_id,
                                              ProjectMember.user_id == member_user_id))
    if m:
        db.delete(m)
        db.commit()


# ---------- documents ----------
def _doc_out(db: Session, d: Document) -> S.DocumentOut:
    o = S.DocumentOut.model_validate(d)
    o.chars = len(d.extracted_text or "")
    o.chunk_count = db.scalar(select(func.count()).where(DocumentChunk.document_id == d.id)) or 0
    return o


@router.get("/projects/{project_id}/documents", response_model=list[S.DocumentOut])
def list_documents(project_id: uuid.UUID, db: Session = Depends(get_db)):
    return [_doc_out(db, d) for d in db.scalars(select(Document).where(Document.project_id == project_id)
                                                 .order_by(Document.created_at))]


@router.post("/projects/{project_id}/documents", response_model=S.DocumentOut, status_code=201,
             dependencies=[AIRateLimit])
async def upload_document(project_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db),
                          user: User = Depends(current_user)):
    from app.core.config import get_settings

    data = await file.read(get_settings().max_upload_mb * 1024 * 1024 + 1)
    return _doc_out(db, docs.ingest(db, project_id, file.filename or "upload.txt", data, user.id))


@router.post("/projects/{project_id}/documents/paste", response_model=S.DocumentOut, status_code=201,
             dependencies=[AIRateLimit])
def paste_document(project_id: uuid.UUID, body: S.PasteIn, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    name = body.title if body.title.endswith((".md", ".txt")) else f"{body.title}.md"
    return _doc_out(db, docs.ingest(db, project_id, name, body.text.encode(), user.id))


@router.get("/documents/{document_id}/chunks", response_model=list[S.ChunkOut])
def get_chunks(document_id: uuid.UUID, db: Session = Depends(get_db)):
    return docs.list_chunks(db, document_id)


@router.post("/chunks/lookup", response_model=list[S.ChunkOut])
def lookup_chunks(ids: list[uuid.UUID], db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = (select(DocumentChunk).join(Document, Document.id == DocumentChunk.document_id)
         .where(DocumentChunk.id.in_(ids[:50])))
    visible = visible_project_ids(db, user)
    if visible is not None:
        q = q.where(Document.project_id.in_(visible))
    return list(db.scalars(q))


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    d = db.get(Document, document_id)
    if d is None:
        raise NotFound("Document")
    check_project(db, user, d.project_id, write=True)
    db.delete(d)
    db.commit()
