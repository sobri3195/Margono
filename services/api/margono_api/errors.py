from fastapi import HTTPException
from pydantic import BaseModel


class ApiError(BaseModel):
    code: str
    message: str


def api_error(
    status: int, code: str, message: str, *, authenticate: bool = False
) -> HTTPException:
    headers = {"WWW-Authenticate": "Bearer"} if authenticate else None
    return HTTPException(
        status, detail=ApiError(code=code, message=message), headers=headers
    )
