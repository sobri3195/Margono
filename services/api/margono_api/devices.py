"""Case-scoped consent and fixture-only device diagnostics."""

from json import loads
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from .errors import api_error
from .operations import (
    CurrentOperator,
    Database,
    IdempotencyKey,
    visible_case,
    write_audit,
)
from .synthetic_worker import DEVICE_TASK, FIXTURES, defer_job
from .workflows import read_job, require_open

router = APIRouter()

DISCLOSURE = (
    "Simulasi menghasilkan metadata fiktif. Tidak ada akses USB, pembacaan perangkat, "
    "atau pengumpulan isi perangkat. Persetujuan untuk simulasi ini dapat dicabut."
)
SCOPE = "Metadata keamanan dari fixture perangkat"


class ConsentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["granted", "declined"]


DEVICE_SESSIONS = """
    SELECT s.id, s.platform, c.status, c.decided_at, c.revoked_at, c.disclosure, c.scope,
           j.id AS job_id, d.evidence, d.evidence_sha256
    FROM synthetic_device_sessions ss JOIN device_sessions s ON s.id = ss.id
    JOIN consent_records c ON c.id = ss.consent_id
    LEFT JOIN jobs j ON j.device_session_id = s.id AND j.kind = 'synthetic_device'
    LEFT JOIN synthetic_device_evidence d ON d.job_id = j.id
    WHERE ss.case_id = :case
"""


def device_view(row) -> dict:
    data = dict(row)
    data["evidence"] = loads(row.evidence) if row.evidence is not None else None
    return data


def device_case(
    db: Database, user: CurrentOperator, case_id: UUID, *, lock: bool = False
):
    case = visible_case(db, user, case_id, lock=lock)
    fixture = FIXTURES[case.synthetic_fixture_id]
    if fixture.workspace != "usb":
        raise api_error(404, "device_fixture_not_found", "Case has no device fixture.")
    return case, fixture


def require_examiner(user: CurrentOperator) -> None:
    if "forensic_examiner" not in user.roles:
        raise api_error(
            403, "device_access_denied", "The Forensic Examiner role is required."
        )


def get_session(db: Database, case_id: UUID, session_id: UUID):
    result = (
        db.execute(
            text(DEVICE_SESSIONS + " AND s.id = :session"),
            {"case": case_id, "session": session_id},
        )
        .mappings()
        .one_or_none()
    )
    if result is None:
        raise api_error(404, "device_session_not_found", "Device session not found.")
    return result


def find_decision(db: Database, case_id: UUID, key: str):
    return db.execute(
        text("""
        SELECT ss.id, s.examiner_id, (SELECT status FROM consent_decisions
            WHERE consent_id = ss.consent_id AND status IN ('granted', 'declined')) AS initial_status
        FROM synthetic_device_sessions ss JOIN device_sessions s ON s.id = ss.id
        WHERE ss.case_id = :case AND ss.creation_key = :key
    """),
        {"case": case_id, "key": key},
    ).one_or_none()


@router.get("/cases/{case_id}/devices")
def case_devices(case_id: UUID, db: Database, user: CurrentOperator):
    _, fixture = device_case(db, user, case_id)
    sessions = db.execute(
        text(DEVICE_SESSIONS + " ORDER BY c.decided_at DESC, s.id LIMIT 100"),
        {"case": case_id},
    ).mappings()
    return {
        "mode": "SYNTHETIC",
        "platform": "iphone" if fixture.reference_id == "DEV-IPHONE" else "android",
        "scope": SCOPE,
        "disclosure": DISCLOSURE,
        "sessions": [device_view(row) for row in sessions],
    }


@router.get("/cases/{case_id}/devices/decision")
def recover_decision(
    case_id: UUID, key: IdempotencyKey, db: Database, user: CurrentOperator
):
    require_examiner(user)
    device_case(db, user, case_id)
    prior = find_decision(db, case_id, key)
    if prior is None or prior.examiner_id != user.id:
        return None
    return device_view(get_session(db, case_id, prior.id))


@router.get("/cases/{case_id}/devices/{session_id}/audit")
def device_audit(case_id: UUID, session_id: UUID, db: Database, user: CurrentOperator):
    device_case(db, user, case_id)
    if "supervisor" not in user.roles:
        raise api_error(403, "device_audit_denied", "The Supervisor role is required.")
    get_session(db, case_id, session_id)
    events = db.execute(
        text("""
            SELECT id, action, occurred_at, correlation_id, actor_id
            FROM audit_events WHERE case_id = :case AND device_session_id = :session
            ORDER BY occurred_at DESC, id DESC LIMIT 100
        """),
        {"case": case_id, "session": session_id},
    ).mappings()
    return [dict(event) for event in events]


@router.post("/cases/{case_id}/devices", status_code=201)
def decide_consent(
    case_id: UUID,
    payload: ConsentInput,
    key: IdempotencyKey,
    request: Request,
    db: Database,
    user: CurrentOperator,
):
    require_examiner(user)
    case, fixture = device_case(db, user, case_id, lock=True)
    prior = find_decision(db, case_id, key)
    if prior is not None:
        if prior.initial_status != payload.status or prior.examiner_id != user.id:
            raise api_error(
                409, "idempotency_conflict", "This key belongs to another decision."
            )
        return device_view(get_session(db, case_id, prior.id))
    require_open(case)
    if fixture.case_id == "SYN-013" and payload.status != "declined":
        raise api_error(
            409,
            "fixture_declines",
            "This fixture simulates the owner declining consent.",
        )

    session_id = db.scalar(
        text("""
        INSERT INTO device_sessions (case_id, examiner_id, platform)
        VALUES (:case, :user, :platform) RETURNING id
    """),
        {
            "case": case_id,
            "user": user.id,
            "platform": "iphone" if fixture.reference_id == "DEV-IPHONE" else "android",
        },
    )
    consent = db.scalar(
        text("""
        INSERT INTO consent_records (session_id, recorded_by_id, purpose, scope, disclosure, status, decided_at)
        VALUES (:session, :user, :purpose, :scope, :disclosure, :status, now()) RETURNING id
    """),
        {
            "session": session_id,
            "user": user.id,
            "purpose": case.purpose,
            "scope": SCOPE,
            "disclosure": DISCLOSURE,
            "status": payload.status,
        },
    )
    db.execute(
        text("""
        INSERT INTO synthetic_device_sessions (case_id, id, consent_id, creation_key)
        VALUES (:case, :session, :consent, :key)
    """),
        {"case": case_id, "session": session_id, "consent": consent, "key": key},
    )
    write_audit(
        db,
        request,
        user.id,
        f"device.consent.{payload.status}",
        case_id,
        device_session_id=session_id,
    )
    return device_view(get_session(db, case_id, session_id))


@router.post("/cases/{case_id}/devices/{session_id}/jobs", status_code=201)
def queue_device(
    case_id: UUID,
    session_id: UUID,
    request: Request,
    db: Database,
    user: CurrentOperator,
):
    require_examiner(user)
    case, _ = device_case(db, user, case_id, lock=True)
    session = get_session(db, case_id, session_id)
    if session.job_id is not None:
        return read_job(db, session.job_id)
    require_open(case)
    if session.status != "granted":
        raise api_error(
            409,
            "consent_required",
            "A granted consent is required for this device session.",
        )
    job_id = db.scalar(
        text("""
        INSERT INTO jobs (case_id, kind, idempotency_key, device_session_id)
        VALUES (:case, 'synthetic_device', :key, :session) RETURNING id
    """),
        {"case": case_id, "session": session_id, "key": str(session_id)},
    )
    queue_id = defer_job(db, job_id, DEVICE_TASK)
    db.execute(
        text("UPDATE jobs SET queue_id = :queue WHERE id = :job"),
        {"queue": queue_id, "job": job_id},
    )
    write_audit(
        db, request, user.id, "job.device.queued", case_id, device_session_id=session_id
    )
    return read_job(db, job_id)


@router.post("/cases/{case_id}/devices/{session_id}/revoke")
def revoke_consent(
    case_id: UUID,
    session_id: UUID,
    request: Request,
    db: Database,
    user: CurrentOperator,
):
    device_case(db, user, case_id, lock=True)
    if not {"forensic_examiner", "supervisor"} & user.roles:
        raise api_error(
            403,
            "device_access_denied",
            "The Forensic Examiner or Supervisor role is required.",
        )
    session = get_session(db, case_id, session_id)
    if session.status == "revoked":
        return device_view(session)
    if session.status != "granted":
        raise api_error(
            409, "consent_not_granted", "Only granted consent can be revoked."
        )
    db.execute(
        text("""
        UPDATE consent_records SET status = 'revoked', revoked_at = now()
        WHERE id = (SELECT consent_id FROM synthetic_device_sessions WHERE id = :session)
    """),
        {"session": session_id},
    )
    if session.job_id:
        job = db.execute(
            text("""
            SELECT j.status, j.queue_id, q.status AS queue_status
            FROM jobs j JOIN procrastinate_jobs q ON q.id = j.queue_id
            WHERE j.id = :job FOR UPDATE OF j, q
        """),
            {"job": session.job_id},
        ).one()
        if job.status == "queued":
            if job.queue_status == "todo":
                db.execute(
                    text("SELECT procrastinate_cancel_job_v1(:queue, false, false)"),
                    {"queue": job.queue_id},
                )
            db.execute(
                text("""
                UPDATE jobs SET status = 'cancelled', failure_code = 'consent_revoked'
                WHERE id = :job
            """),
                {"job": session.job_id},
            )
    write_audit(
        db,
        request,
        user.id,
        "device.consent.revoked",
        case_id,
        device_session_id=session_id,
    )
    return device_view(get_session(db, case_id, session_id))
