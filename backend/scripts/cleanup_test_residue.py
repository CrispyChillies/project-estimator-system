"""List (default) or delete guest accounts and projects left by release checks.

  uv run python -m scripts.cleanup_test_residue            # dry run: lists matches only
  uv run python -m scripts.cleanup_test_residue --confirm  # deletes exactly what the dry run listed

Matches: non-admin, non-archived guest users (email *@guest.calibr) named 'Release check', 'curl check' or
'CALIBR-RUN-*', and projects named 'Release check *', 'curl proj' or 'CALIBR-RUN-*'. Refuses (exit 2) if a matched
project is owned by anyone other than a matched guest, or a matched guest owns any other project.
"""

import sys
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings  # noqa: E402
from app.db.models import Project, User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.services.accounts import GUEST_DOMAIN, purge_guest  # noqa: E402

USER_NAMES = ("Release check", "curl check")
PROJECT_NAMES = ("curl proj",)
PREFIX = "CALIBR-RUN-"


def _user_filter():
    return (User.role == "member", User.archived.is_(False), User.email.ilike(f"%{GUEST_DOMAIN}"),
            or_(User.name.in_(USER_NAMES), User.name.like(f"{PREFIX}%")))


def _project_filter():
    return or_(Project.name.like("Release check %"), Project.name.in_(PROJECT_NAMES), Project.name.like(f"{PREFIX}%"))


def find(db: Session) -> tuple[list[User], list[Project], list[str]]:
    users = list(db.scalars(select(User).where(*_user_filter()).order_by(User.created_at)))
    projects = list(db.scalars(select(Project).where(_project_filter()).order_by(Project.created_at)))
    ids = {u.id for u in users}
    problems = []
    for p in projects:
        if p.owner_id not in ids or p.is_archive:
            problems.append(f"project '{p.name}' ({p.id}) is not owned by a matched guest (owner {p.owner_id})")
    matched = {p.id for p in projects}
    for u in users:
        others = [p for p in db.scalars(select(Project).where(Project.owner_id == u.id)) if p.id not in matched]
        if others:
            problems.append(f"guest '{u.name}' ({u.id}) also owns {len(others)} unmatched project(s)")
    return users, projects, problems


def main() -> int:
    confirm = "--confirm" in sys.argv
    url = urlparse(get_settings().database_url)
    print(f"database: {url.hostname}{url.path} ({'DELETE' if confirm else 'dry run'})")
    with SessionLocal() as db:
        users, projects, problems = find(db)
        names = {u.id: u.name for u in users}
        print(f"\nusers ({len(users)}):")
        for u in users:
            print(f"  {u.id}  {u.created_at:%Y-%m-%d %H:%M}  {u.email}  {u.name}")
        print(f"\nprojects ({len(projects)}):")
        for p in projects:
            print(f"  {p.id}  {p.created_at:%Y-%m-%d %H:%M}  owner={names.get(p.owner_id, p.owner_id)}  {p.name}")
        if problems:
            print("\nREFUSING:\n  " + "\n  ".join(problems))
            return 2
        if not confirm:
            print(f"\nmatched {len(users)} users and {len(projects)} projects; nothing deleted (use --confirm)")
            return 0
        for u in users:
            purge_guest(db, u)
        print(f"\ndeleted {len(users)} users and {len(projects)} projects")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
