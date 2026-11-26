import asyncio
from unittest.mock import AsyncMock

import pytest
from procrastinate.exceptions import ConnectorException
from psycopg import OperationalError, ProgrammingError

from margono_api import synthetic_worker
from margono_api.database import DatabaseUnavailable


def test_continuous_worker_reconnects_with_bounded_backoff(monkeypatch):
    connector_error = ConnectorException()
    connector_error.__cause__ = OperationalError("connection closed")
    session = AsyncMock(
        side_effect=[
            ExceptionGroup("worker session", [DatabaseUnavailable(), connector_error]),
            *[DatabaseUnavailable() for _ in range(5)],
            None,
        ]
    )
    sleep = AsyncMock()
    monkeypatch.setattr(synthetic_worker, "worker_session", session)
    monkeypatch.setattr(synthetic_worker.asyncio, "sleep", sleep)

    asyncio.run(synthetic_worker.run_worker())

    assert session.await_count == 7
    assert [call.args[0] for call in sleep.await_args_list] == [1, 2, 4, 8, 15, 15]


@pytest.mark.parametrize(
    ("once", "failure"),
    [
        (True, DatabaseUnavailable()),
        (
            False,
            ExceptionGroup(
                "worker session", [DatabaseUnavailable(), ProgrammingError()]
            ),
        ),
    ],
)
def test_worker_does_not_retry_one_shot_or_non_connection_errors(
    monkeypatch, once, failure
):
    session = AsyncMock(side_effect=failure)
    monkeypatch.setattr(synthetic_worker, "worker_session", session)

    with pytest.raises(type(failure)) as raised:
        asyncio.run(synthetic_worker.run_worker(once=once))

    assert raised.value is failure
    session.assert_awaited_once_with(once=once)
