import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user_id
from app.db.models import ChangeProposal
from app.db.session import get_db
from app.schemas import api as S
from app.services import proposals as pr
from app.services.summary import compute_summary

router = APIRouter(tags=["agent"])


@router.get("/estimates/{estimate_id}/proposals", response_model=list[S.ProposalOut])
def list_proposals(estimate_id: uuid.UUID, status: str | None = None, db: Session = Depends(get_db)):
    q = select(ChangeProposal).where(ChangeProposal.estimate_id == estimate_id).order_by(ChangeProposal.created_at.desc())
    if status:
        q = q.where(ChangeProposal.status == status)
    return list(db.scalars(q))


@router.get("/proposals/{proposal_id}", response_model=S.ProposalOut)
def get_proposal(proposal_id: uuid.UUID, db: Session = Depends(get_db)):
    return pr.get_proposal(db, proposal_id)


def _finish(db: Session, prop) -> ChangeProposal:
    compute_summary(db, prop.estimate_id)
    db.commit()
    return prop


@router.post("/proposals/{proposal_id}/ops/{op_id}/accept", response_model=S.ProposalOut)
def accept_op(proposal_id: uuid.UUID, op_id: str, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    return _finish(db, pr.resolve_op(db, proposal_id, op_id, True, uid))


@router.post("/proposals/{proposal_id}/ops/{op_id}/reject", response_model=S.ProposalOut)
def reject_op(proposal_id: uuid.UUID, op_id: str, body: S.ReasonIn | None = None, db: Session = Depends(get_db),
              uid=Depends(current_user_id)):
    return _finish(db, pr.resolve_op(db, proposal_id, op_id, False, uid, body.reason_text if body else None))


@router.post("/proposals/{proposal_id}/accept_all", response_model=S.ProposalOut)
def accept_all(proposal_id: uuid.UUID, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    return _finish(db, pr.resolve_all(db, proposal_id, True, uid))


@router.post("/proposals/{proposal_id}/reject_all", response_model=S.ProposalOut)
def reject_all(proposal_id: uuid.UUID, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    return _finish(db, pr.resolve_all(db, proposal_id, False, uid))
