import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from app.schemas import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, error: RequestValidationError) -> JSONResponse:
        payload = ErrorResponse(
            code="validation_error",
            message="Nieprawidłowe parametry żądania",
            details=[
                ErrorDetail(location=list(item["loc"]), message=item["msg"], type=item["type"])
                for item in error.errors()
            ],
        )
        return JSONResponse(status_code=422, content=payload.model_dump(mode="json"))

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, error: HTTPException) -> JSONResponse:
        detail = error.detail
        payload = ErrorResponse(
            code=detail.get("code", "http_error") if isinstance(detail, dict) else "http_error",
            message=detail.get("message", "Błąd żądania")
            if isinstance(detail, dict)
            else str(detail),
        )
        return JSONResponse(
            status_code=error.status_code,
            content=payload.model_dump(mode="json"),
            headers=error.headers,
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_request: Request, error: SQLAlchemyError) -> JSONResponse:
        logger.error("Database request failed", exc_info=error)
        return JSONResponse(
            status_code=503,
            content=ErrorResponse(
                code="database_unavailable", message="Baza danych jest niedostępna"
            ).model_dump(mode="json"),
        )
