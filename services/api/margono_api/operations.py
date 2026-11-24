from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from secrets import token_urlsafe
from threading import BoundedSemaphore
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from .csv_imports import (
    CsvColumns,
    CsvContent,
    CsvInput,
    CsvPreview,
    csv_reader,
    preview_csv,
    read_columns,
)
from .database import database_transaction
from .errors import api_error
from .fixtures import CATALOG
from .passwords import verify_password


def private_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/v1", dependencies=[Depends(private_response)])
Database = Annotated[Connection, Depends(database_transaction, scope="function")]
Bearer = Annotated[
    HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))
]
OperatorName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")]
CaseText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
]
FixtureId = Annotated[str, StringConstraints(pattern=r"^SYN-[0-9]{3}$")]
CASE_OPERATORS = {"osint_analyst", "forensic_examiner"}
FIXTURE_IDS = frozenset(case.case_id for case in CATALOG.cases)
PASSWORD_WORKERS = BoundedSemaphore(2)
CASE_COLUMNS = (
    "id, owner_id, synthetic_fixture_id, purpose, scope, status, created_at, closed_at"
)


class Credentials(BaseModel):
    username: OperatorName
    password: str = Field(min_length=1, max_length=256)


class SessionToken(BaseModel):
    token: str
    user_id: UUID
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    roles: list[str]


class CaseInput(BaseModel):
    fixture_id: FixtureId
    purpose: CaseText
    scope: CaseText


class CaseView(BaseModel):
    id: UUID
    owner_id: UUID
    synthetic_fixture_id: str
    purpose: str
    scope: str
    status: Literal["open", "closed"]
    created_at: datetime
    closed_at: datetime | None


@dataclass(frozen=True)
class Operator:
    id: UUID
    username: str
    roles: frozenset[str]
    digest: bytes


def auth_required():
    return api_error(
        401,
        "invalid_credentials",
        "Valid operator credentials are required.",
        authenticate=True,
    )


def signed_in(db: Database, bearer: Bearer) -> Operator:
    if (
        bearer is None
        or len(bearer.credentials) != 43
        or not bearer.credentials.isascii()
    ):
        raise auth_required()

    digest = sha256(bearer.credentials.encode()).digest()
    user = (
        db.execute(
            text("""SELECT u.id, u.username
                FROM user_sessions s JOIN users u ON s.user_id = u.id
                WHERE s.token_digest = :digest AND s.expires_at > now()
                AND u.disabled_at IS NULL"""),
            {"digest": digest},
        )
        .mappings()
        .one_or_none()
    )
    if user is None:
        raise auth_required()
    roles = db.scalars(
        text("SELECT role_slug FROM user_roles WHERE user_id = :id"), {"id": user.id}
    )
    return Operator(user.id, user.username, frozenset(roles), digest)


CurrentOperator = Annotated[Operator, Depends(signed_in, scope="function")]


def write_audit(
    db: Connection,
    request: Request,
    operator_id: UUID,
    action: str,
    case_id: UUID | None = None,
):
    db.execute(
        text("""INSERT INTO audit_events (case_id, actor_id, action, correlation_id)
                       VALUES (:case, :actor, :action, :correlation)"""),
        {
            "case": case_id,
            "actor": operator_id,
            "action": action,
            "correlation": UUID(request.state.correlation_id),
        },
    )


@router.post("/sessions", status_code=201)
def login(
    credentials: Credentials, request: Request, response: Response, db: Database
) -> SessionToken:
    if not PASSWORD_WORKERS.acquire(blocking=False):
        raise api_error(429, "login_busy", "Try signing in again shortly.")
    try:
        user = (
            db.execute(
                text(
                    "SELECT id, password_hash FROM users WHERE username = :name AND disabled_at IS NULL"
                ),
                {"name": credentials.username},
            )
            .mappings()
            .one_or_none()
        )
        if not verify_password(
            credentials.password, user.password_hash if user is not None else None
        ):
            raise auth_required()
    finally:
        PASSWORD_WORKERS.release()

    token = token_urlsafe(32)
    db.execute(
        text("DELETE FROM user_sessions WHERE user_id = :id AND expires_at <= now()"),
        {"id": user.id},
    )
    expires_at = db.scalar(
        text("""INSERT INTO user_sessions (token_digest, user_id, expires_at)
                                  VALUES (:digest, :id, now() + interval '1 hour') RETURNING expires_at"""),
        {"digest": sha256(token.encode()).digest(), "id": user.id},
    )
    write_audit(db, request, user.id, "session.created")
    roles = db.scalars(
        text("SELECT role_slug FROM user_roles WHERE user_id = :id ORDER BY role_slug"),
        {"id": user.id},
    )
    return SessionToken(
        token=token, user_id=user.id, expires_at=expires_at, roles=list(roles)
    )


@router.delete("/sessions/current", status_code=204)
def logout(request: Request, db: Database, user: CurrentOperator) -> None:
    db.execute(
        text("DELETE FROM user_sessions WHERE token_digest = :digest"),
        {"digest": user.digest},
    )
    write_audit(db, request, user.id, "session.revoked")


def case_condition(user: Operator) -> str:
    if "supervisor" in user.roles:
        return "TRUE"
    if CASE_OPERATORS & user.roles:
        return "owner_id = :owner"
    raise api_error(403, "case_access_denied", "This role cannot access cases.")


def visible_case(
    db: Connection, user: Operator, case_id: UUID, *, lock: bool = False
) -> RowMapping:
    scope = case_condition(user)
    row = (
        db.execute(
            text(
                f"SELECT {CASE_COLUMNS} FROM cases WHERE id = :id AND synthetic_fixture_id IS NOT NULL AND ({scope})"
                + (" FOR UPDATE" if lock else "")
            ),
            {"id": case_id, "owner": user.id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise api_error(404, "case_not_found", "Case not found.")
    return row


@router.post("/cases", status_code=201)
def create_case(
    payload: CaseInput, request: Request, db: Database, user: CurrentOperator
) -> CaseView:
    if not CASE_OPERATORS & user.roles:
        raise api_error(403, "case_access_denied", "This role cannot create cases.")
    if payload.fixture_id not in FIXTURE_IDS:
        raise api_error(404, "case_not_found", "Synthetic fixture not found.")
    row = (
        db.execute(
            text(f"""INSERT INTO cases (owner_id, synthetic_fixture_id, purpose, scope)
                VALUES (:owner, :fixture, :purpose, :scope) RETURNING {CASE_COLUMNS}"""),
            {
                "owner": user.id,
                "fixture": payload.fixture_id,
                "purpose": payload.purpose,
                "scope": payload.scope,
            },
        )
        .mappings()
        .one()
    )
    write_audit(db, request, user.id, "case.created", row.id)
    return CaseView.model_validate(dict(row))


@router.get("/cases")
def list_cases(db: Database, user: CurrentOperator) -> list[CaseView]:
    scope = case_condition(user)
    rows = db.execute(
        text(f"""SELECT {CASE_COLUMNS} FROM cases WHERE synthetic_fixture_id IS NOT NULL AND ({scope})
                ORDER BY created_at DESC, id LIMIT 100"""),
        {"owner": user.id},
    ).mappings()
    return [CaseView.model_validate(dict(row)) for row in rows]


@router.get("/cases/{case_id}")
def get_case(case_id: UUID, db: Database, user: CurrentOperator) -> CaseView:
    return CaseView.model_validate(dict(visible_case(db, user, case_id)))


@router.patch("/cases/{case_id}/status")
def set_case_status(
    case_id: UUID,
    status: Literal["open", "closed"],
    request: Request,
    db: Database,
    user: CurrentOperator,
) -> CaseView:
    if "supervisor" not in user.roles:
        raise api_error(
            403, "case_access_denied", "A Supervisor must change case status."
        )
    row = visible_case(db, user, case_id, lock=True)
    if row.status != status:
        row = (
            db.execute(
                text(f"""UPDATE cases SET status = :status,
                     closed_at = CASE WHEN :status = 'closed' THEN clock_timestamp() ELSE NULL END
                     WHERE id = :id RETURNING {CASE_COLUMNS}"""),
                {"status": status, "id": case_id},
            )
            .mappings()
            .one()
        )
        write_audit(db, request, user.id, f"case.{status}", case_id)
    return CaseView.model_validate(dict(row))


class ImportCounts(BaseModel):
    row_count: int
    valid_count: int
    invalid_count: int


class ImportResult(ImportCounts):
    id: UUID
    sha256: str


class ImportSummary(ImportCounts):
    id: UUID
    created_at: datetime
    selected_column: str | None
    sha256: str | None
    submitted_by_id: UUID


class ImportPage(BaseModel):
    items: list[ImportSummary]
    next_cursor: UUID | None


IMPORT_SUMMARY = """
    SELECT i.id, i.created_at, i.selected_column, i.submitted_by_id, e.sha256,
           stats.row_count, stats.valid_count, stats.invalid_count
    FROM imports i
    LEFT JOIN import_evidence e ON e.import_id = i.id
    CROSS JOIN LATERAL (
        SELECT count(*) AS row_count,
               count(*) FILTER (WHERE status = 'valid') AS valid_count,
               count(*) FILTER (WHERE status = 'invalid') AS invalid_count
        FROM import_rows WHERE import_id = i.id
    ) stats
    WHERE i.case_id = :case
"""


def require_import_access(
    db: Connection, user: Operator, case_id: UUID, *, lock: bool = False
) -> RowMapping:
    if "osint_analyst" not in user.roles:
        raise api_error(
            403, "import_access_denied", "The OSINT Analyst role is required."
        )
    row = visible_case(db, user, case_id, lock=lock)
    if row.owner_id != user.id:
        raise api_error(404, "case_not_found", "Case not found.")
    return row


@router.get("/cases/{case_id}/imports")
def list_imports(
    case_id: UUID,
    db: Database,
    user: CurrentOperator,
    before: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ImportPage:
    visible_case(db, user, case_id)
    cutoff = ""
    params = {"case": case_id, "limit": limit + 1}
    if before is not None:
        cursor = db.execute(
            text("SELECT created_at FROM imports WHERE case_id = :case AND id = :id"),
            {"case": case_id, "id": before},
        ).one_or_none()
        if cursor is None:
            raise api_error(404, "import_not_found", "Import cursor not found.")
        cutoff = " AND (i.created_at, i.id) < (:created_at, :id)"
        params.update(created_at=cursor.created_at, id=before)
    rows = (
        db.execute(
            text(
                IMPORT_SUMMARY
                + cutoff
                + " ORDER BY i.created_at DESC, i.id DESC LIMIT :limit"
            ),
            params,
        )
        .mappings()
        .all()
    )
    return ImportPage(
        items=[ImportSummary.model_validate(row) for row in rows[:limit]],
        next_cursor=rows[limit - 1].id if len(rows) > limit else None,
    )


@router.post("/cases/{case_id}/imports/columns")
def import_columns(
    case_id: UUID,
    payload: CsvContent,
    db: Database,
    user: CurrentOperator,
) -> CsvColumns:
    require_import_access(db, user, case_id)
    _, parser = csv_reader(payload.content)
    return CsvColumns(columns=read_columns(parser))


@router.post("/cases/{case_id}/imports/preview")
def preview_import(
    case_id: UUID, payload: CsvInput, db: Database, user: CurrentOperator
) -> CsvPreview:
    require_import_access(db, user, case_id)
    return preview_csv(payload)[1]


@router.post("/cases/{case_id}/imports", status_code=201)
def confirm_import(
    case_id: UUID,
    payload: CsvInput,
    request: Request,
    db: Database,
    user: CurrentOperator,
    key: Annotated[
        str, Header(alias="Idempotency-Key", pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    ],
) -> ImportResult:
    case = require_import_access(db, user, case_id, lock=True)
    digest = sha256(payload.content.encode()).hexdigest()
    prior = (
        db.execute(
            text(IMPORT_SUMMARY + " AND i.idempotency_key = :key"),
            {"case": case_id, "key": key},
        )
        .mappings()
        .one_or_none()
    )
    if prior is not None:
        if (prior.sha256, prior.selected_column) != (digest, payload.column):
            raise api_error(
                409, "idempotency_conflict", "This key belongs to a different import."
            )
        return ImportResult.model_validate(prior)
    if case.status != "open":
        raise api_error(409, "case_closed", "Reopen the case before importing.")

    content, preview = preview_csv(payload)
    batch = db.scalar(
        text("""
        INSERT INTO imports (case_id, submitted_by_id, source_ref, selected_column, idempotency_key)
        VALUES (:case, :user, :source, :column, :key) RETURNING id
    """),
        {
            "case": case_id,
            "user": user.id,
            "source": f"sha256:{digest}",
            "column": payload.column,
            "key": key,
        },
    )
    db.execute(
        text(
            "INSERT INTO import_evidence (import_id, content, sha256) VALUES (:import_id, :content, :sha)"
        ),
        {"import_id": batch, "content": content, "sha": digest},
    )
    db.execute(
        text("""INSERT INTO import_rows (import_id, row_number, reference_label, status)
                      VALUES (:import_id, :row_number, :reference_label, :status)"""),
        [
            {**row.model_dump(exclude={"duplicate"}), "import_id": batch}
            for row in preview.rows
        ],
    )
    write_audit(db, request, user.id, "import.confirmed", case_id)
    valid = sum(row.status == "valid" for row in preview.rows)
    return ImportResult(
        id=batch,
        sha256=digest,
        row_count=len(preview.rows),
        valid_count=valid,
        invalid_count=len(preview.rows) - valid,
    )


@router.get("/cases/{case_id}/imports/{import_id}/evidence")
def import_evidence(
    case_id: UUID, import_id: UUID, db: Database, user: CurrentOperator
) -> Response:
    visible_case(db, user, case_id)
    row = db.execute(
        text("""
        SELECT e.content, e.sha256 FROM import_evidence e JOIN imports i ON i.id=e.import_id
        WHERE i.case_id=:case AND e.import_id=:id
    """),
        {"case": case_id, "id": import_id},
    ).one_or_none()
    if row is None:
        raise api_error(404, "evidence_not_found", "Import evidence not found.")
    if sha256(row.content).hexdigest() != row.sha256:
        raise api_error(
            409, "evidence_integrity_error", "The evidence failed verification."
        )
    return Response(
        row.content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": 'attachment; filename="original.csv.bin"',
            "Cache-Control": "no-store",
            "X-Content-SHA256": row.sha256,
        },
    )
