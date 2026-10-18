import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user_id
from app.core.errors import NotFound
from app.db.models import Document, DocumentChunk, Project
from app.db.session import get_db
from app.schemas import api as S
from app.services import documents as docs
from app.services.views import project_list

router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=list[S.ProjectListItem])
def list_projects(status: str | None = None, search: str | None = None, db: Session = Depends(get_db)):
    return project_list(db, status, search)


@router.post("/projects", response_model=S.ProjectOut, status_code=201)
def create_project(body: S.ProjectIn, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    p = Project(**body.model_dump(), status="draft", data_source="user", created_by=uid)
    db.add(p)
    db.commit()
    return p


@router.get("/projects/{project_id}", response_model=S.ProjectOut)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if p is None:
        raise NotFound("Project")
    return p


@router.patch("/projects/{project_id}", response_model=S.ProjectOut)
def patch_project(project_id: uuid.UUID, body: S.ProjectPatch, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if p is None:
        raise NotFound("Project")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    return p


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: uuid.UUID, db: Session = Depends(get_db)):
    p = db.get(Project, project_id)
    if p is None:
        raise NotFound("Project")
    db.delete(p)
    db.commit()


def _doc_out(db: Session, d: Document) -> S.DocumentOut:
    o = S.DocumentOut.model_validate(d)
    o.chars = len(d.extracted_text or "")
    o.chunk_count = db.scalar(select(func.count()).where(DocumentChunk.document_id == d.id)) or 0
    return o


@router.get("/projects/{project_id}/documents", response_model=list[S.DocumentOut])
def list_documents(project_id: uuid.UUID, db: Session = Depends(get_db)):
    return [_doc_out(db, d) for d in db.scalars(select(Document).where(Document.project_id == project_id)
                                                 .order_by(Document.created_at))]


@router.post("/projects/{project_id}/documents", response_model=S.DocumentOut, status_code=201)
async def upload_document(project_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db),
                          uid=Depends(current_user_id)):
    from app.core.config import get_settings

    data = await file.read(get_settings().max_upload_mb * 1024 * 1024 + 1)
    return _doc_out(db, docs.ingest(db, project_id, file.filename or "upload.txt", data, uid))


@router.post("/projects/{project_id}/documents/paste", response_model=S.DocumentOut, status_code=201)
def paste_document(project_id: uuid.UUID, body: S.PasteIn, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    name = body.title if body.title.endswith((".md", ".txt")) else f"{body.title}.md"
    return _doc_out(db, docs.ingest(db, project_id, name, body.text.encode(), uid))


@router.get("/documents/{document_id}/chunks", response_model=list[S.ChunkOut])
def get_chunks(document_id: uuid.UUID, db: Session = Depends(get_db)):
    return docs.list_chunks(db, document_id)


@router.post("/chunks/lookup", response_model=list[S.ChunkOut])
def lookup_chunks(ids: list[uuid.UUID], db: Session = Depends(get_db)):
    return list(db.scalars(select(DocumentChunk).where(DocumentChunk.id.in_(ids[:50]))))


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: uuid.UUID, db: Session = Depends(get_db)):
    d = db.get(Document, document_id)
    if d is None:
        raise NotFound("Document")
    db.delete(d)
    db.commit()
