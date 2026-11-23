from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .fixtures import CATALOG, CaseFixture, Catalog

app = FastAPI(
    title="MARGONO Simulation API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)
CASES_BY_ID = {case.case_id: case for case in CATALOG.cases}


class CaseNotFound(BaseModel):
    code: str = "case_not_found"
    message: str = "Synthetic case not found."


@app.middleware("http")
async def correlation_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = str(uuid4())
    return response


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "SYNTHETIC"}


@app.get("/api/v1/simulation/catalog")
def catalog() -> Catalog:
    return CATALOG


@app.get(
    "/api/v1/simulation/cases/{case_id}",
    response_model=CaseFixture,
    responses={404: {"model": CaseNotFound}},
)
def case_detail(case_id: str) -> CaseFixture | JSONResponse:
    case = CASES_BY_ID.get(case_id)
    if case is None:
        return JSONResponse(status_code=404, content=CaseNotFound().model_dump())
    return case
