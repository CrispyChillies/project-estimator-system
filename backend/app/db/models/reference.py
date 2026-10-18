from typing import Any

from sqlalchemy import Float, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import enums as E
from app.db.base import Base, IdMixin, TimestampMixin, enum_check


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (enum_check("users", "role", E.USER_ROLES),)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    role: Mapped[str] = mapped_column(String(20), default="pm")


class DeliveryRole(IdMixin, TimestampMixin, Base):
    __tablename__ = "delivery_roles"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    hourly_rate: Mapped[float] = mapped_column(Float, default=50.0)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    color: Mapped[str] = mapped_column(String(20), default="#64748b")


class TaskCategory(IdMixin, TimestampMixin, Base):
    __tablename__ = "task_categories"
    key: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500), default="")


class Setting(TimestampMixin, Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
