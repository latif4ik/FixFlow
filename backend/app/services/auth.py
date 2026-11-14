import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.errors import TooManyRequests, Unauthorized
from app.core.security import (
    DUMMY_HASH,
    hash_email,
    hash_token,
    new_token,
    verify_password,
)
from app.models.identity import Membership, Organization, SecurityEvent, Session, User
from app.services.security_events import record_security_event

RATE_WINDOW = timedelta(minutes=15)
MAX_FAILURES_PER_EMAIL = 10
MAX_FAILURES_PER_IP = 30
LOGIN_FAILED = "login_failed"


@dataclass
class LoginResult:
    token: str
    session: Session
    user: User
    memberships: list[tuple[Membership, Organization]]


def active_memberships(db: DbSession, user_id: uuid.UUID) -> list[tuple[Membership, Organization]]:
    rows = db.execute(
        select(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .where(
            Membership.user_id == user_id,
            Membership.is_active.is_(True),
            Organization.is_active.is_(True),
        )
        .order_by(Organization.name, Membership.id)
    ).all()
    return [(m, o) for m, o in rows]


def _failures(db: DbSession, *, email_hash: str | None = None, ip: str | None = None) -> int:
    since = datetime.now(UTC) - RATE_WINDOW
    stmt = (
        select(func.count())
        .select_from(SecurityEvent)
        .where(SecurityEvent.event_type == LOGIN_FAILED, SecurityEvent.created_at >= since)
    )
    if email_hash is not None:
        stmt = stmt.where(SecurityEvent.email_hash == email_hash)
    if ip is not None:
        stmt = stmt.where(SecurityEvent.ip == ip)
    return db.scalar(stmt) or 0


def login(
    db: DbSession, email: str, password: str, ip: str | None, user_agent: str | None
) -> LoginResult:
    email = email.strip().lower()
    email_hash = hash_email(email)

    # DB-based throttle: shared by every worker process.
    if _failures(db, email_hash=email_hash) >= MAX_FAILURES_PER_EMAIL or (
        ip is not None and _failures(db, ip=ip) >= MAX_FAILURES_PER_IP
    ):
        record_security_event(db, "login_rate_limited", email_hash=email_hash, ip=ip)
        db.commit()
        raise TooManyRequests("Too many failed sign-in attempts. Try again later.")

    user = db.scalars(select(User).where(User.email == email)).first()
    password_ok = verify_password(user.password_hash if user else DUMMY_HASH, password)
    if user is None or not password_ok or not user.is_active:
        reason = (
            "unknown_email" if user is None else "bad_password" if not password_ok else "inactive"
        )
        record_security_event(
            db,
            LOGIN_FAILED,
            user_id=user.id if user else None,
            email_hash=email_hash,
            ip=ip,
            details={"reason": reason},
        )
        db.commit()
        raise Unauthorized("Invalid email or password.")

    token = new_token()
    now = datetime.now(UTC)
    session = Session(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=now + timedelta(minutes=get_settings().SESSION_TTL_MINUTES),
        last_used_at=now,
        user_agent=user_agent[:300] if user_agent else None,
    )
    db.add(session)
    record_security_event(db, "login_succeeded", user_id=user.id, email_hash=email_hash, ip=ip)
    db.commit()
    db.refresh(session)
    return LoginResult(token, session, user, active_memberships(db, user.id))


def revoke_session(db: DbSession, session: Session, ip: str | None, reason: str = "logout") -> None:
    if session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
    record_security_event(
        db, "session_revoked", user_id=session.user_id, ip=ip, details={"reason": reason}
    )


def revoke_all_sessions(db: DbSession, user_id: uuid.UUID, reason: str) -> int:
    result = db.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    count = getattr(result, "rowcount", 0) or 0
    record_security_event(
        db, "sessions_revoked_all", user_id=user_id, details={"reason": reason, "count": count}
    )
    return count
