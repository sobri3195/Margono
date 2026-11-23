from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.exceptions import HTTPException

from .fixtures import CATALOG, CaseFixture, Catalog, Variation, generate_variation


class ApiError(BaseModel):
    code: str
    message: str


class PlanQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int = Field(ge=-(2**31), le=2**31 - 1)


app = FastAPI(
    title="MARGONO Simulation API",
    version="1.1.0",
    description=(
        "Read-only API for synthetic cybersecurity fixtures. "
        "The catalog provides synthetic case IDs. The plan endpoint accepts only a numeric seed."
    ),
    docs_url=None,
    redoc_url=None,
    responses={500: {"model": ApiError}},
)
CASES_BY_ID = {case.case_id: case for case in CATALOG.cases}
CORRELATION_HEADER = "X-Correlation-ID"
ROUTING_ERRORS = {
    HTTPStatus.NOT_FOUND: ApiError(code="not_found", message="Resource not found."),
    HTTPStatus.METHOD_NOT_ALLOWED: ApiError(
        code="method_not_allowed", message="Method not allowed."
    ),
}


@app.middleware("http")
async def correlation_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request.state.correlation_id = str(uuid4())
    response = await call_next(request)
    response.headers[CORRELATION_HEADER] = request.state.correlation_id
    return response


@app.exception_handler(HTTPException)
async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
    error = exc.detail
    if not isinstance(error, ApiError):
        error = ROUTING_ERRORS.get(exc.status_code) or ApiError(
            code="http_error", message="Request could not be completed."
        )
    return JSONResponse(
        error.model_dump(), status_code=exc.status_code, headers=exc.headers
    )


@app.exception_handler(RequestValidationError)
async def invalid_request(
    _request: Request, _exc: RequestValidationError
) -> JSONResponse:
    error = ApiError(code="invalid_request", message="Request parameters are invalid.")
    return JSONResponse(error.model_dump(), status_code=422)


@app.exception_handler(Exception)
async def internal_error(request: Request, _exc: Exception) -> JSONResponse:
    error = ApiError(code="internal_error", message="An internal error occurred.")
    trace_id = getattr(request.state, "correlation_id", None) or str(uuid4())
    return JSONResponse(
        error.model_dump(), status_code=500, headers={CORRELATION_HEADER: trace_id}
    )


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "SYNTHETIC"}


@app.get("/api/v1/simulation/catalog")
def catalog() -> Catalog:
    return CATALOG


@app.get(
    "/api/v1/simulation/cases/{case_id}",
    responses={404: {"model": ApiError}, 422: {"model": ApiError}},
)
def case_detail(case_id: str) -> CaseFixture:
    case = CASES_BY_ID.get(case_id)
    if case is None:
        raise HTTPException(
            status_code=404,
            detail=ApiError(code="case_not_found", message="Synthetic case not found."),
        )
    return case


@app.get("/api/v1/simulation/plans", responses={422: {"model": ApiError}})
def simulation_plan(query: Annotated[PlanQuery, Query()]) -> Variation:
    return generate_variation(query.seed)
