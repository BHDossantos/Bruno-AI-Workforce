"""New tables only for opt-in, capacity-reserved calling. No default activation."""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class CallHandler(Base):
    __tablename__ = "call_handlers"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    states: Mapped[list] = mapped_column(JSONB, nullable=False)
    authorization_ref: Mapped[str] = mapped_column(String, nullable=False)
    verified_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    available_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class CallPermit(Base):
    __tablename__ = "call_permits"
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), primary_key=True)
    phone: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)
    recipient_timezone: Mapped[str] = mapped_column(String, nullable=False)
    authorization_ref: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CallReservation(Base):
    __tablename__ = "call_reservations"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    handler_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("call_handlers.id"), nullable=False)
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), nullable=False)
    phone: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    provider_id: Mapped[str | None] = mapped_column(String, unique=True)
    result: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CallLeadHold(Base):
    __tablename__ = "call_lead_holds"
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("leads.id"), primary_key=True)
    reservation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("call_reservations.id"), unique=True, nullable=False)
