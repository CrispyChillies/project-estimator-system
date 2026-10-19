import uuid

from fastapi import APIRouter, Depends, File, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user_id
from app.core.errors import NotFound
from app.db.models import UnplannedActual
from app.db.session import get_db
from app.schemas import api as S
from app.services import actuals as ac
from app.services.learning import deliver_project

router = APIRouter(tags=["actuals"])


@router.get("/projects/{project_id}/actuals", response_model=list[S.ActualRow])
def list_actuals(project_id: uuid.UUID, db: Session = Depends(get_db)):
    return [S.ActualRow(task_id=t.id, module=m.name, title=t.title, min_hours=t.min_hours, max_hours=t.max_hours,
                        actual_hours=a.actual_hours if a else None, note=a.note if a else None)
            for t, m, a in ac.final_tasks(db, project_id)]


@router.put("/projects/{project_id}/actuals", status_code=204)
def upsert_actuals(project_id: uuid.UUID, body: list[S.ActualIn], db: Session = Depends(get_db), uid=Depends(current_user_id)):
    for row in body:
        ac.upsert_actual(db, project_id, row.task_id, row.actual_hours, uid, "manual", row.note)
    db.commit()


@router.get("/projects/{project_id}/actuals/template.csv")
def actuals_template(project_id: uuid.UUID, db: Session = Depends(get_db)):
    return Response(ac.csv_template(db, project_id), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="actuals.csv"'})


@router.post("/projects/{project_id}/actuals/import")
async def import_actuals(project_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db),
                         uid=Depends(current_user_id)) -> dict:
    res = ac.import_csv(db, project_id, await file.read(5 * 1024 * 1024), uid)
    db.commit()
    return res


@router.get("/projects/{project_id}/unplanned", response_model=list[S.UnplannedOut])
def list_unplanned(project_id: uuid.UUID, db: Session = Depends(get_db)):
    return list(db.scalars(select(UnplannedActual).where(UnplannedActual.project_id == project_id)))


@router.post("/projects/{project_id}/unplanned", response_model=S.UnplannedOut, status_code=201)
def add_unplanned(project_id: uuid.UUID, body: S.UnplannedIn, db: Session = Depends(get_db)):
    u = ac.add_unplanned(db, project_id, body.title, body.hours, body.category_id, body.note)
    db.commit()
    return u


@router.delete("/unplanned/{unplanned_id}", status_code=204)
def delete_unplanned(unplanned_id: uuid.UUID, db: Session = Depends(get_db)):
    u = db.get(UnplannedActual, unplanned_id)
    if u is None:
        raise NotFound("Unplanned work")
    db.delete(u)
    db.commit()


@router.post("/projects/{project_id}/deliver", response_model=S.ProjectOut)
def deliver(project_id: uuid.UUID, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    p = deliver_project(db, project_id, user_id=uid)
    db.commit()
    return p


@router.get("/projects/{project_id}/accuracy")
def project_accuracy(project_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    return ac.accuracy(db, project_id)
