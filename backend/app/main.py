from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.balloons.router import router as balloon_router
from app.errors.api import api_error, error_responses
from app.exports.router import router as export_router
from app.projects.router import router as project_router
from app.projects.schemas import HealthResponse
from app.review.router import router as review_router


app = FastAPI(title="Quality Inspection", version="0.1.0")
app.include_router(project_router)
app.include_router(review_router)
app.include_router(balloon_router)
app.include_router(export_router)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request,
    error: RequestValidationError,
):
    return api_error(
        422,
        "request_validation_failed",
        "request validation failed",
        severity="blocking",
        stage="request_validation",
        location_ref=request.url.path,
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(
    request: Request,
    error: StarletteHTTPException,
):
    code = "route_not_found" if error.status_code == 404 else "http_error"
    message = "route was not found" if error.status_code == 404 else str(error.detail)
    return api_error(
        error.status_code,
        code,
        message,
        severity="blocking",
        stage="http_routing",
        location_ref=request.url.path,
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(
    request: Request,
    error: Exception,
):
    return api_error(
        500,
        "internal_server_error",
        "internal server error",
        severity="fatal",
        stage="api",
        location_ref=request.url.path,
    )


@app.get(
    "/api/v1/health",
    operation_id="QI-API-SYS-001",
    response_model=HealthResponse,
    responses=error_responses({500: ("internal_server_error",)}),
)
def health() -> HealthResponse:
    return HealthResponse(status="ok", app_name="quality-inspection")
