"""Procrastinate worker for deterministic fixture evidence."""

import argparse
import asyncio
import json
from hashlib import sha256
from logging import getLogger
from os import environ
from time import monotonic
from uuid import UUID

from procrastinate import App, JobContext, PsycopgConnector, RetryStrategy
from procrastinate.exceptions import ConnectorException
from psycopg import OperationalError
from sqlalchemy import text
from sqlalchemy.engine import Connection, make_url

from .database import DatabaseUnavailable, open_database
from .fixtures import CATALOG

QUEUE = "margono-synthetic"
SOURCE_TASK = "margono.synthetic_source"
DEVICE_TASK = "margono.synthetic_device"
WORKER_TIMEOUT_SECONDS = 30
MAX_RECOVERIES = 3
MAX_RECONNECT_DELAY = 15
FIXTURES = {fixture.case_id: fixture for fixture in CATALOG.cases}
logger = getLogger(__name__)


class FixtureTimeout(Exception):
    pass


def defer_job(db: Connection, job_id: UUID, task: str) -> int:
    # Keep the domain job and Procrastinate dispatch in the same transaction.
    return db.scalar(
        text("""
            SELECT (procrastinate_defer_jobs_v2(ARRAY[
                ROW(:queue, :task, 0, NULL, NULL,
                    jsonb_build_object('job_id', CAST(:job AS text)), NULL, NULL
                )::procrastinate_job_to_defer_v2
            ]))[1]
        """),
        {"queue": QUEUE, "task": task, "job": job_id},
    )


def recover_interrupted_jobs() -> None:
    with open_database() as db:
        db.execute(
            text("SELECT procrastinate_prune_stalled_workers_v1(:timeout)"),
            {"timeout": WORKER_TIMEOUT_SECONDS},
        )
        jobs = db.execute(
            text("""
                SELECT id, attempts FROM procrastinate_jobs
                WHERE queue_name = :queue AND status = 'doing' AND worker_id IS NULL
                FOR UPDATE SKIP LOCKED
            """),
            {"queue": QUEUE},
        )
        for queue_id, attempts in jobs:
            if attempts >= MAX_RECOVERIES:
                db.execute(
                    text("SELECT procrastinate_finish_job_v1(:id, 'failed', false)"),
                    {"id": queue_id},
                )
            else:
                db.execute(
                    text(
                        "SELECT procrastinate_retry_job_v2(:id, now(), NULL, NULL, NULL)"
                    ),
                    {"id": queue_id},
                )


def get_app() -> App:
    if environ.get("MARGONO_MODE", "simulation") != "simulation":
        raise RuntimeError("This worker supports MARGONO_MODE=simulation only.")
    url = make_url(environ["MARGONO_DATABASE_URL"])
    if url.drivername != "postgresql+psycopg":
        raise ValueError("Expected a PostgreSQL URL using psycopg.")
    conninfo = url.set(drivername="postgresql").render_as_string(hide_password=False)
    app = App(
        connector=PsycopgConnector(
            conninfo=conninfo, timeout=5, kwargs={"connect_timeout": 2}
        )
    )

    @app.task(
        name=SOURCE_TASK,
        queue=QUEUE,
        pass_context=True,
        retry=RetryStrategy(
            max_attempts=3,
            exponential_wait=2,
            retry_exceptions=(FixtureTimeout, DatabaseUnavailable),
        ),
    )
    def generate_evidence(context: JobContext, job_id: str) -> None:
        process_source(UUID(job_id), context)

    @app.task(
        name=DEVICE_TASK,
        queue=QUEUE,
        pass_context=True,
        retry=RetryStrategy(
            max_attempts=3, exponential_wait=2, retry_exceptions=(DatabaseUnavailable,)
        ),
    )
    def record_device(context: JobContext, job_id: str) -> None:
        process_device(UUID(job_id), context)

    return app


def process_source(job_id: UUID, context: JobContext) -> None:
    timeout = False
    with open_database() as db:
        case = db.execute(
            text("""
                SELECT c.id, c.synthetic_fixture_id, c.status
                FROM cases c JOIN jobs j ON j.case_id = c.id
                WHERE j.id = :job FOR UPDATE OF c
            """),
            {"job": job_id},
        ).one()
        job = db.execute(
            text("""
                SELECT j.status, j.import_id, e.sha256, e.content
                FROM jobs j JOIN import_evidence e ON e.import_id = j.import_id
                JOIN procrastinate_jobs q ON q.id = j.queue_id
                WHERE j.id = :job AND q.id = :queue_id AND q.status = 'doing'
                    AND q.worker_id = :worker AND q.attempts = :attempts
                FOR UPDATE OF j, q
            """),
            {
                "job": job_id,
                "queue_id": context.job.id,
                "worker": context.job.worker_id,
                "attempts": context.job.attempts,
            },
        ).one_or_none()
        if job is None or job.status != "queued":
            return

        fixture = FIXTURES[case.synthetic_fixture_id]
        failure = None
        if case.status != "open":
            failure = "case_closed"
        elif sha256(job.content).hexdigest() != job.sha256:
            failure = "evidence_integrity_error"
        elif fixture.reference_id == "SRC-TIMEOUT" and context.job.attempts == 0:
            timeout = True
            failure = "fixture_timeout"

        if failure is None:
            # The import hash provides provenance. Labels never enter the adapter.
            evidence = json.dumps(
                {
                    "mode": "SYNTHETIC",
                    "version": 1,
                    "fixture_id": fixture.case_id,
                    "source_ref": "SRC-FIXTURE",
                    "observed_at": fixture.created_at.isoformat(),
                    "indicator": "margono.test",
                    "limitation": "Fixture deterministik. Tidak menetapkan identitas atau risiko seseorang.",
                    "import_id": str(job.import_id),
                    "import_sha256": job.sha256,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            threat = {
                "SYN-009": "inconclusive",
                "SYN-010": "false_positive",
            }.get(fixture.case_id, "suspected")
            db.execute(
                text("""
                    INSERT INTO synthetic_findings (job_id, evidence, evidence_sha256, threat_status, severity)
                    VALUES (:job, :evidence, :sha, :threat, 'low')
                """),
                {
                    "job": job_id,
                    "evidence": evidence,
                    "sha": sha256(evidence.encode()).hexdigest(),
                    "threat": threat,
                },
            )
        status = "queued" if timeout else "failed" if failure else "completed"
        db.execute(
            text(
                "UPDATE jobs SET status = :status, failure_code = :failure WHERE id = :job"
            ),
            {"status": status, "failure": failure, "job": job_id},
        )
        db.execute(
            text("""
                INSERT INTO audit_events (case_id, import_id, action)
                VALUES (:case, :import_id, :action)
            """),
            {
                "case": case.id,
                "import_id": job.import_id,
                "action": "job.source." + (failure or "completed"),
            },
        )
    if timeout:
        raise FixtureTimeout("Synthetic source timeout")


def process_device(job_id: UUID, context: JobContext) -> None:
    with open_database() as db:
        case = db.execute(
            text("""
            SELECT c.id, c.synthetic_fixture_id, c.status
            FROM cases c JOIN jobs j ON j.case_id = c.id
            WHERE j.id = :job FOR UPDATE OF c
        """),
            {"job": job_id},
        ).one()
        job = db.execute(
            text("""
            SELECT j.status, s.platform, cr.status AS consent_status, cr.id AS consent_id,
                   cr.scope, s.id AS session_id
            FROM jobs j JOIN synthetic_device_sessions sd ON sd.id = j.device_session_id
            JOIN device_sessions s ON s.id = sd.id
            JOIN consent_records cr ON cr.id = sd.consent_id
            JOIN procrastinate_jobs q ON q.id = j.queue_id
            WHERE j.id = :job AND q.id = :queue_id AND q.status = 'doing'
                AND q.worker_id = :worker AND q.attempts = :attempts
            FOR UPDATE OF j, q
        """),
            {
                "job": job_id,
                "queue_id": context.job.id,
                "worker": context.job.worker_id,
                "attempts": context.job.attempts,
            },
        ).one_or_none()
        if job is None or job.status != "queued":
            return

        fixture = FIXTURES[case.synthetic_fixture_id]
        failure = None
        if case.status != "open":
            status, failure = "failed", "case_closed"
        elif job.consent_status != "granted":
            status, failure = "cancelled", "consent_required"
        elif fixture.case_id == "SYN-015":
            status, failure = "failed", "fixture_disconnected"
        else:
            status = "completed"
            result = "unsupported" if job.platform == "iphone" else "sample_available"
            evidence = json.dumps(
                {
                    "mode": "SYNTHETIC",
                    "version": 1,
                    "fixture_id": fixture.case_id,
                    "source_ref": fixture.reference_id,
                    "observed_at": fixture.created_at.isoformat(),
                    "platform": job.platform,
                    "result": result,
                    "scope": job.scope,
                    "session_id": str(job.session_id),
                    "consent_id": str(job.consent_id),
                    "limitation": "Hasil simulasi tidak menentukan apakah perangkat aman.",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            db.execute(
                text("""
                INSERT INTO synthetic_device_evidence (job_id, evidence, evidence_sha256)
                VALUES (:job, :evidence, :sha)
            """),
                {
                    "job": job_id,
                    "evidence": evidence,
                    "sha": sha256(evidence.encode()).hexdigest(),
                },
            )
        db.execute(
            text(
                "UPDATE jobs SET status = :status, failure_code = :failure WHERE id = :job"
            ),
            {"status": status, "failure": failure, "job": job_id},
        )
        db.execute(
            text("""
                INSERT INTO audit_events (case_id, device_session_id, action)
                VALUES (:case, :session, :action)
            """),
            {
                "case": case.id,
                "session": job.session_id,
                "action": f"job.device.{failure or 'completed'}",
            },
        )


async def worker_session(*, once: bool) -> None:
    app = get_app()

    # A live worker also recovers a peer that exits without closing its claim.
    async def recover_periodically() -> None:
        while True:
            await asyncio.sleep(10)
            await asyncio.to_thread(recover_interrupted_jobs)

    await asyncio.to_thread(recover_interrupted_jobs)
    async with app.open_async():
        if once:
            await app.run_worker_async(queues=[QUEUE], wait=False, listen_notify=False)
        else:
            async with asyncio.TaskGroup() as tasks:
                recovery = tasks.create_task(recover_periodically())
                try:
                    await app.run_worker_async(queues=[QUEUE], listen_notify=False)
                finally:
                    recovery.cancel()


def is_connection_failure(error: BaseException) -> bool:
    if isinstance(error, ExceptionGroup):
        return all(is_connection_failure(item) for item in error.exceptions)
    if isinstance(error, ConnectorException) and error.__cause__ is not None:
        return is_connection_failure(error.__cause__)
    if isinstance(error, OperationalError):
        state = error.sqlstate
        return (
            state is None
            or state.startswith("08")
            or state in {"57P01", "57P02", "57P03"}
        )
    return isinstance(error, DatabaseUnavailable)


async def run_worker(*, once: bool = False) -> None:
    delay = 1
    while True:
        started = monotonic()
        try:
            await worker_session(once=once)
            return
        except Exception as error:
            if once or not is_connection_failure(error):
                raise
            if monotonic() - started >= WORKER_TIMEOUT_SECONDS:
                delay = 1
            logger.warning(
                "PostgreSQL connection lost. Retrying worker in %d seconds.", delay
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_RECONNECT_DELAY)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="Drain currently runnable jobs and exit."
    )
    asyncio.run(run_worker(once=parser.parse_args().once))


if __name__ == "__main__":
    main()
