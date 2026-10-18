from __future__ import annotations

import csv
import io
import uuid

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DeliveryRole, Module, Task, TaskCategory
from app.services import estimates as es
from app.services.calibration import mid
from app.services.summary import ensure_summary

HEADER = ["Module", "Task", "Category", "Role", "Min h", "Max h", "Mid h", "Rate", "Cost (mid)", "Confidence", "Origin"]


def _rows(db: Session, estimate_id: uuid.UUID) -> list[list]:
    q = (select(Task, Module, TaskCategory.name, DeliveryRole)
         .join(Module, Module.id == Task.module_id)
         .outerjoin(TaskCategory, TaskCategory.id == Task.category_id)
         .outerjoin(DeliveryRole, DeliveryRole.id == Task.delivery_role_id)
         .where(Task.estimate_id == estimate_id).order_by(Module.position, Task.position))
    out = []
    for t, m, cat, role in db.execute(q):
        if not es.is_effectively_included(t, m.removed):
            continue
        rate = role.hourly_rate if role else 0
        out.append([m.name, t.title, cat or "", role.name if role else "", t.min_hours, t.max_hours,
                    mid(t.min_hours, t.max_hours), rate, mid(t.min_hours, t.max_hours) * rate, t.confidence, t.origin])
    return out


def to_csv(db: Session, estimate_id: uuid.UUID) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEADER)
    w.writerows(_rows(db, estimate_id))
    return buf.getvalue()


def to_xlsx(db: Session, estimate_id: uuid.UUID) -> bytes:
    est = es.get_estimate(db, estimate_id)
    rows = _rows(db, estimate_id)
    wb = Workbook()
    flat = wb.active
    flat.title = "Tasks"
    flat.append(HEADER)
    for c in flat[1]:
        c.font = Font(bold=True)
    for r in rows:
        flat.append(r)
    st = wb.create_sheet("Structured")
    current = None
    for r in rows:
        if r[0] != current:
            current = r[0]
            st.append([current])
            st.cell(st.max_row, 1).font = Font(bold=True)
        st.append(["", *r[1:]])
    sm = wb.create_sheet("Summary")
    s = ensure_summary(db, est)
    sim = s.get("simulation", {})
    for k, v in [("Version", est.version), ("Status", est.status), ("Total min", s.get("total_min")),
                 ("Total max", s.get("total_max")), ("P50", sim.get("p50")), ("P80", sim.get("p80")),
                 ("P90", sim.get("p90")), ("Cost (mid)", s.get("total_cost_mid"))]:
        sm.append([k, v])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
