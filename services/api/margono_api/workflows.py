"""Authenticated fixture jobs, review, and report endpoints."""

from collections import Counter
from json import loads
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from .errors import api_error
from .operations import (
    CASE_OPERATORS,
    CaseText,
    CurrentOperator,
    Database,
    IdempotencyKey,
    OperatorName,
    case_condition,
    require_import_access,
    visible_case,
    write_audit,
)
from .synthetic_worker import FIXTURES, SOURCE_TASK, defer_job

router = APIRouter()

JOB_COLUMNS = """
    j.id, j.case_id, j.kind, j.import_id, j.device_session_id, j.created_at, j.failure_code,
    CASE WHEN j.status <> 'queued' THEN j.status
        WHEN q.status = 'doing' THEN 'running'
        WHEN q.status = 'failed' THEN 'failed'
        ELSE 'queued' END AS status,
    COALESCE(q.attempts, 0) AS attempts, q.scheduled_at,
    EXISTS (SELECT 1 FROM synthetic_findings f WHERE f.job_id = j.id AND f.verification = 'pending') AS review_pending
"""
JOB_FROM = " FROM jobs j LEFT JOIN procrastinate_jobs q ON q.id = j.queue_id "
FINDINGS = """
    SELECT f.id, j.id AS job_id, j.import_id, f.evidence, f.evidence_sha256,
           f.threat_status, f.severity, f.verification, f.review_note, f.reviewed_at
    FROM synthetic_findings f JOIN jobs j ON j.id = f.job_id WHERE j.case_id = :case
"""


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verification: Literal["verified", "inconclusive", "rejected"]
    note: CaseText
    expected: Literal["pending", "verified", "inconclusive", "rejected"]


def scoped_import(db: Database, case_id: UUID, import_id: UUID) -> None:
    if not db.scalar(
        text("""
            SELECT EXISTS (
                SELECT 1 FROM imports i JOIN import_evidence e ON e.import_id = i.id
                WHERE i.case_id = :case AND i.id = :id
            )
        """),
        {"case": case_id, "id": import_id},
    ):
        raise api_error(404, "import_not_found", "Import not found.")


def require_open(case) -> None:
    if case.status != "open":
        raise api_error(409, "case_closed", "Reopen the case before making changes.")


@router.get("/cases/{case_id}/imports/{import_id}/details")
def import_details(case_id: UUID, import_id: UUID, db: Database, user: CurrentOperator):
    visible_case(db, user, case_id)
    scoped_import(db, case_id, import_id)
    rows = db.execute(
        text("""
            SELECT row_number, reference_label, status FROM import_rows
            WHERE import_id = :id ORDER BY row_number
        """),
        {"id": import_id},
    ).mappings()
    events = db.execute(
        text("""
            SELECT action, occurred_at, correlation_id FROM audit_events
            WHERE case_id = :case AND import_id = :id
            ORDER BY occurred_at DESC, id DESC LIMIT 100
        """),
        {"case": case_id, "id": import_id},
    ).mappings()
    entries = [dict(row) for row in rows]
    labels = Counter(
        item["reference_label"].casefold()
        for item in entries
        if item["reference_label"] is not None
    )
    for row in entries:
        label = row["reference_label"]
        row["duplicate"] = label is not None and labels[label.casefold()] > 1
    return {"rows": entries, "events": [dict(row) for row in events]}


@router.put("/cases/{case_id}/collaborators/{username}", status_code=204)
@router.delete("/cases/{case_id}/collaborators/{username}", status_code=204)
def set_collaborator(
    case_id: UUID,
    username: OperatorName,
    request: Request,
    db: Database,
    user: CurrentOperator,
) -> None:
    if "supervisor" not in user.roles:
        raise api_error(403, "collaboration_denied", "The Supervisor role is required.")
    case = visible_case(db, user, case_id, lock=True)
    require_open(case)
    if request.method == "DELETE":
        changed = db.execute(
            text("""
                DELETE FROM case_collaborators WHERE case_id = :case
                    AND user_id = (SELECT id FROM users WHERE username = :name)
            """),
            {"case": case_id, "name": username},
        ).rowcount
        action = "case.collaborator_revoked"
    else:
        collaborator = db.scalar(
            text("""
                SELECT u.id FROM users u JOIN user_roles r ON r.user_id = u.id
                WHERE u.username = :name AND u.disabled_at IS NULL AND r.role_slug IN ('osint_analyst', 'forensic_examiner')
                LIMIT 1
            """),
            {"name": username},
        )
        if not collaborator or collaborator == case.owner_id:
            raise api_error(
                404, "collaborator_not_found", "Eligible collaborator not found."
            )
        changed = db.execute(
            text("""
                INSERT INTO case_collaborators (case_id, user_id)
                VALUES (:case, :user) ON CONFLICT DO NOTHING
            """),
            {"case": case_id, "user": collaborator},
        ).rowcount
        action = "case.collaborator_granted"
    if changed:
        write_audit(db, request, user.id, action, case_id)


@router.get("/cases/{case_id}/collaborators")
def collaborators(case_id: UUID, db: Database, user: CurrentOperator):
    visible_case(db, user, case_id)
    return list(
        db.scalars(
            text("""
        SELECT u.username FROM case_collaborators c JOIN users u ON c.user_id = u.id
        WHERE c.case_id = :case ORDER BY u.username
    """),
            {"case": case_id},
        )
    )


def read_job(db: Database, job_id: UUID) -> dict:
    return dict(
        db.execute(
            text("SELECT " + JOB_COLUMNS + JOB_FROM + "WHERE j.id = :job"),
            {"job": job_id},
        )
        .mappings()
        .one()
    )


@router.post("/cases/{case_id}/imports/{import_id}/jobs", status_code=201)
def queue_source(
    case_id: UUID,
    import_id: UUID,
    request: Request,
    db: Database,
    user: CurrentOperator,
    key: IdempotencyKey,
):
    case = require_import_access(db, user, case_id, lock=True)
    scoped_import(db, case_id, import_id)
    prior = db.execute(
        text("""
        SELECT id, import_id FROM jobs
        WHERE case_id = :case AND kind = 'synthetic_source' AND idempotency_key = :key
    """),
        {"case": case_id, "key": key},
    ).one_or_none()
    if prior is not None:
        if prior.import_id != import_id:
            raise api_error(
                409, "idempotency_conflict", "This key belongs to a different import."
            )
        return read_job(db, prior.id)
    require_open(case)
    if not db.scalar(
        text("""
        SELECT EXISTS (SELECT 1 FROM import_rows WHERE import_id = :id AND status = 'valid')
    """),
        {"id": import_id},
    ):
        raise api_error(409, "no_valid_rows", "The batch needs at least one valid row.")

    job_id = db.scalar(
        text("""
        INSERT INTO jobs (case_id, kind, idempotency_key, import_id)
        VALUES (:case, 'synthetic_source', :key, :import_id) RETURNING id
    """),
        {"case": case_id, "key": key, "import_id": import_id},
    )
    queue_id = defer_job(db, job_id, SOURCE_TASK)
    db.execute(
        text("UPDATE jobs SET queue_id = :queue WHERE id = :job"),
        {"queue": queue_id, "job": job_id},
    )
    write_audit(db, request, user.id, "job.source.queued", case_id, import_id=import_id)
    return read_job(db, job_id)


@router.get("/cases/{case_id}/jobs")
def case_jobs(case_id: UUID, db: Database, user: CurrentOperator):
    visible_case(db, user, case_id)
    return [
        dict(row)
        for row in db.execute(
            text(
                "SELECT "
                + JOB_COLUMNS
                + JOB_FROM
                + """
            WHERE j.case_id = :case AND j.kind IN ('synthetic_source', 'synthetic_device')
            ORDER BY j.created_at DESC, j.id DESC LIMIT 100
        """
            ),
            {"case": case_id},
        ).mappings()
    ]


@router.get("/jobs")
def portal_jobs(db: Database, user: CurrentOperator):
    if not (CASE_OPERATORS | {"supervisor"}) & user.roles:
        return []
    condition = case_condition(user)
    return [
        dict(row)
        for row in db.execute(
            text(
                "SELECT "
                + JOB_COLUMNS
                + JOB_FROM
                + f"""
            WHERE j.kind IN ('synthetic_source', 'synthetic_device') AND j.case_id IN (
                SELECT id FROM cases WHERE synthetic_fixture_id IS NOT NULL AND ({condition})
            ) AND (j.status IN ('queued', 'paused', 'failed') OR j.created_at > now() - interval '24 hours')
            ORDER BY (j.status IN ('queued', 'paused', 'failed')) DESC, j.created_at DESC, j.id DESC LIMIT 100
        """
            ),
            {"owner": user.id},
        ).mappings()
    ]


@router.patch("/cases/{case_id}/jobs/{job_id}")
def control_job(
    case_id: UUID,
    job_id: UUID,
    request: Request,
    db: Database,
    user: CurrentOperator,
    action: Literal["pause", "resume", "cancel", "retry"],
):
    case = visible_case(db, user, case_id, lock=True)
    if not {"supervisor", "osint_analyst"} & user.roles:
        raise api_error(
            403,
            "job_access_denied",
            "The OSINT Analyst or Supervisor role is required.",
        )
    job = db.execute(
        text("""
        SELECT j.status, j.import_id, j.queue_id, q.status AS queue_status
        FROM jobs j JOIN procrastinate_jobs q ON q.id = j.queue_id
        WHERE j.id = :job AND j.case_id = :case AND j.kind = 'synthetic_source'
        FOR UPDATE OF j, q
    """),
        {"job": job_id, "case": case_id},
    ).one_or_none()
    if job is None:
        raise api_error(404, "job_not_found", "Job not found.")

    params = {"job": job_id, "queue": job.queue_id}
    status = None
    if (
        action in {"pause", "cancel"}
        and job.status == "queued"
        and job.queue_status == "todo"
    ):
        db.execute(
            text("SELECT procrastinate_cancel_job_v1(:queue, false, false)"), params
        )
        status = "paused" if action == "pause" else "cancelled"
    elif action == "cancel" and job.status == "paused":
        status = "cancelled"
    elif (action == "resume" and job.status == "paused") or (
        action == "retry" and (job.status == "failed" or job.queue_status == "failed")
    ):
        require_open(case)
        params["queue"] = defer_job(db, job_id, SOURCE_TASK)
        db.execute(
            text(
                "UPDATE jobs SET queue_id = :queue, failure_code = NULL WHERE id = :job"
            ),
            params,
        )
        status = "queued"
    if status is None:
        raise api_error(
            409,
            "job_transition_denied",
            "This action is unavailable in the current job state.",
        )
    db.execute(
        text("UPDATE jobs SET status = :status WHERE id = :job"),
        {**params, "status": status},
    )
    write_audit(
        db, request, user.id, f"job.source.{action}", case_id, import_id=job.import_id
    )
    return read_job(db, job_id)


def finding_view(row) -> dict:
    return {**row, "evidence": loads(row["evidence"])}


@router.get("/cases/{case_id}/findings")
def findings(
    case_id: UUID,
    db: Database,
    user: CurrentOperator,
    verification: Annotated[
        Literal["pending", "verified", "inconclusive", "rejected"] | None, Query()
    ] = None,
):
    visible_case(db, user, case_id)
    return [
        finding_view(row)
        for row in db.execute(
            text(
                FINDINGS
                + " AND (CAST(:status AS text) IS NULL OR f.verification = :status) ORDER BY f.id LIMIT 100"
            ),
            {"case": case_id, "status": verification},
        ).mappings()
    ]


@router.patch("/cases/{case_id}/findings/{finding_id}/review")
def review_finding(
    case_id: UUID,
    finding_id: UUID,
    payload: Review,
    request: Request,
    db: Database,
    user: CurrentOperator,
):
    case = visible_case(db, user, case_id, lock=True)
    if not {"osint_analyst", "supervisor"} & user.roles:
        raise api_error(
            403,
            "review_access_denied",
            "The OSINT Analyst or Supervisor role is required.",
        )
    require_open(case)
    params = {"case": case_id, "id": finding_id}
    finding = (
        db.execute(text(FINDINGS + " AND f.id = :id"), params).mappings().one_or_none()
    )
    if finding is None:
        raise api_error(404, "finding_not_found", "Finding not found.")
    if finding["verification"] != "pending":
        if (
            finding["verification"] == payload.verification
            and finding["review_note"] == payload.note
        ):
            return finding_view(finding)
        raise api_error(
            409, "review_conflict", "Another decision was already recorded."
        )
    if payload.expected != "pending":
        raise api_error(409, "review_conflict", "The review state has changed.")
    db.execute(
        text("""
        UPDATE synthetic_findings SET verification = :status, review_note = :note,
            reviewed_by = :user, reviewed_at = now() WHERE id = :id
    """),
        {
            **params,
            "status": payload.verification,
            "note": payload.note,
            "user": user.id,
        },
    )
    write_audit(
        db,
        request,
        user.id,
        f"finding.{payload.verification}",
        case_id,
        import_id=finding["import_id"],
    )
    return finding_view(
        db.execute(text(FINDINGS + " AND f.id = :id"), params).mappings().one()
    )


@router.get("/cases/{case_id}/reports/{template}")
def report(
    case_id: UUID,
    template: Literal["executive", "technical"],
    db: Database,
    user: CurrentOperator,
):
    case = visible_case(db, user, case_id, lock=True)
    device_examiner = (
        "forensic_examiner" in user.roles
        and FIXTURES[case.synthetic_fixture_id].workspace == "usb"
    )
    if template == "technical" and not (
        device_examiner or {"osint_analyst", "supervisor"} & user.roles
    ):
        raise api_error(
            403,
            "technical_report_denied",
            "This role cannot read the technical report for this workspace.",
        )
    summary = (
        db.execute(
            text("""
        SELECT verification, severity, count(*) AS count
        FROM synthetic_findings f JOIN jobs j ON j.id = f.job_id
        WHERE j.case_id = :case GROUP BY verification, severity ORDER BY verification, severity
    """),
            {"case": case_id},
        )
        .mappings()
        .all()
    )
    result = {
        "mode": "SYNTHETIC",
        "case_id": case_id,
        "fixture_id": case.synthetic_fixture_id,
        "template": template,
        "status": case.status,
        "summary": [dict(row) for row in summary],
    }
    devices = db.execute(
        text("""
        SELECT j.id, j.status, j.failure_code, d.evidence, d.evidence_sha256
        FROM jobs j LEFT JOIN synthetic_device_evidence d ON d.job_id = j.id
        WHERE j.case_id = :case AND j.kind = 'synthetic_device'
        ORDER BY j.created_at DESC, j.id
    """),
        {"case": case_id},
    ).mappings()
    device_results = [
        {
            **row,
            "evidence": loads(row["evidence"]) if row["evidence"] is not None else None,
        }
        for row in devices
    ]
    result["device_summary"] = [
        {"status": status, "count": count}
        for status, count in sorted(
            Counter(item["status"] for item in device_results).items()
        )
    ]
    if template == "technical":
        result["device_jobs"] = device_results
        result["findings"] = [
            finding_view(row)
            for row in db.execute(
                text(FINDINGS + " ORDER BY f.id"), {"case": case_id}
            ).mappings()
        ]
    return result
