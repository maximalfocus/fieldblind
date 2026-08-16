"""SQLite persistence for the fictional claim, plus the disposable fixture reset.

The persistence model is deliberately *not* the public contract. Nothing in this module serializes a
claim for a caller or binds caller-supplied keys onto one.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from fieldblind.domain import CLAIM_FIXTURE

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


class Base(DeclarativeBase):
    """Declarative base for the demonstration schema."""


class ClaimRecord(Base):
    """The stored expense claim. Column order matches the canonical property order."""

    __tablename__ = "claims"

    claim_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    employee_id: Mapped[str] = mapped_column(String(32))
    merchant: Mapped[str] = mapped_column(String(64))
    amount_cents: Mapped[int]
    purpose: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16))
    submitted_on: Mapped[str] = mapped_column(String(10))
    risk_score: Mapped[int]
    reviewer_note: Mapped[str] = mapped_column(String(200))
    decision: Mapped[str] = mapped_column(String(16))
    approved_amount_cents: Mapped[int | None] = mapped_column(nullable=True)


def create_database_engine(database_path: Path) -> Engine:
    """Create the engine for one disposable SQLite database file."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite+pysqlite:///{database_path}", future=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the session factory used for one request at a time."""
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def reset_state(engine: Engine) -> None:
    """Drop, recreate, and reseed the disposable fixture so every case starts fresh."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as session, session.begin():
        session.add(
            ClaimRecord(
                claim_id=CLAIM_FIXTURE.claim_id,
                employee_id=CLAIM_FIXTURE.employee_id,
                merchant=CLAIM_FIXTURE.merchant,
                amount_cents=CLAIM_FIXTURE.amount_cents,
                purpose=CLAIM_FIXTURE.purpose,
                status=CLAIM_FIXTURE.status,
                submitted_on=CLAIM_FIXTURE.submitted_on,
                risk_score=CLAIM_FIXTURE.risk_score,
                reviewer_note=CLAIM_FIXTURE.reviewer_note,
                decision=CLAIM_FIXTURE.decision,
                approved_amount_cents=CLAIM_FIXTURE.approved_amount_cents,
            ),
        )


def load_claim(session: Session, claim_id: str) -> ClaimRecord | None:
    """Load one claim by its identifier, or return ``None`` when it does not exist."""
    return session.get(ClaimRecord, claim_id)
