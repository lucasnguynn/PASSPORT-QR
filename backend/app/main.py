from collections.abc import Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler

from app.modules.passport.router import admin_router as passport_admin_router
from app.modules.passport.router import router as passport_router
from app.modules.qr.router import router as qr_router
from app.modules.qr.router import limiter
from app.modules.social.router import admin_router as social_admin_router
from app.modules.social.router import router as social_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(title="Digital Product Passport API", version="0.1.0")
    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    application.add_middleware(SlowAPIMiddleware)
    application.include_router(passport_router)
    application.include_router(passport_admin_router)
    application.include_router(social_router)
    application.include_router(social_admin_router)
    application.include_router(qr_router)

    @application.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; camera 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response

    @application.get("/health", tags=["operations"])
    async def health() -> dict[str, str]:
        """Report process health for container orchestration."""
        return {"status": "healthy"}

    @application.exception_handler(HTTPException)
    async def http_problem(request: Request, exc: HTTPException) -> JSONResponse:
        """Represent intentional HTTP failures as RFC 7807 Problem Details."""
        return JSONResponse(
            status_code=exc.status_code,
            media_type="application/problem+json",
            headers=exc.headers,
            content={
                "type": "about:blank",
                "title": str(exc.detail),
                "status": exc.status_code,
                "detail": str(exc.detail),
                "instance": request.url.path,
            },
        )

    @application.exception_handler(RequestValidationError)
    async def validation_problem(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Represent invalid API input as RFC 7807 Problem Details."""
        return JSONResponse(
            status_code=422,
            media_type="application/problem+json",
            content={
                "type": "https://dpp.local/problems/validation-error",
                "title": "Request validation failed",
                "status": 422,
                "detail": "One or more request values are invalid.",
                "instance": request.url.path,
                "errors": jsonable_encoder(exc.errors()),
            },
        )

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        """Return unexpected failures in RFC 7807 Problem Details format."""
        return JSONResponse(
            status_code=500,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": "Internal Server Error",
                "status": 500,
                "detail": "An unexpected error occurred.",
                "instance": str(request.url.path),
            },
        )

    return application


app = create_app()
