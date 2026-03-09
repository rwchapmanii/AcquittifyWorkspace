import hmac
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.requests import Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.rate_limit import InMemoryRateLimiter, RedisRateLimiter, get_request_ip
from app.api.routes.auth import router as auth_router
from app.core.config import get_settings
from app.api.routes.ingest import router as ingest_router
from app.api.routes.learning import router as learning_router
from app.api.routes.witnesses import router as witnesses_router
from app.api.routes.exhibits import router as exhibits_router
from app.api.routes.uploads import router as uploads_router
from app.api.routes.matters import router as matters_router
from app.api.routes.documents import router as documents_router
from app.api.routes.search import router as search_router
from app.api.routes.ontology import router as ontology_router
from app.api.routes.agent import router as agent_router
from app.api.routes.admin_caselaw import router as admin_caselaw_router

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version)


def _expand_origin_aliases(origins: list[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()

    def add(origin: str) -> None:
        normalized = origin.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        expanded.append(normalized)

    for origin in origins:
        add(origin)
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue

        host = parsed.hostname
        port_suffix = f":{parsed.port}" if parsed.port else ""
        alias_host = None
        if host.startswith("www."):
            alias_host = host[4:]
        elif host.count(".") == 1:
            alias_host = f"www.{host}"

        if alias_host:
            add(f"{parsed.scheme}://{alias_host}{port_suffix}")

    return expanded


cors_origins = settings.cors_allow_origins
if cors_origins:
    configured_origins = [origin.strip() for origin in cors_origins.split(",") if origin.strip()]
else:
    configured_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
allowed_origins = _expand_origin_aliases(configured_origins)


def _set_vary_origin(response: Response) -> None:
    existing_vary = response.headers.get("Vary")
    if not existing_vary:
        response.headers["Vary"] = "Origin"
        return
    vary_values = {value.strip() for value in existing_vary.split(",") if value.strip()}
    if "Origin" not in vary_values:
        response.headers["Vary"] = f"{existing_vary}, Origin"


def _apply_cors_headers(
    request: Request,
    response: Response,
    *,
    expose_retry_after: bool = False,
) -> None:
    origin = request.headers.get("origin")
    if not origin or origin not in allowed_origins:
        return
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    if expose_retry_after:
        response.headers["Access-Control-Expose-Headers"] = "Retry-After"
    _set_vary_origin(response)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

csrf_exempt_paths = {
    "/auth/login",
    "/auth/register",
    "/auth/password/forgot",
    "/auth/password/reset",
    "/auth/mfa/login/verify",
    "/healthz",
    "/version",
}
csrf_safe_methods = {"GET", "HEAD", "OPTIONS"}

rate_limited_paths = {
    path.strip()
    for path in settings.auth_rate_limit_paths.split(",")
    if path.strip()
}
if settings.auth_rate_limit_backend.lower() == "redis" and settings.redis_url:
    auth_rate_limiter = RedisRateLimiter(
        redis_url=settings.redis_url,
        max_attempts=settings.auth_rate_limit_max_attempts,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )
else:
    auth_rate_limiter = InMemoryRateLimiter(
        max_attempts=settings.auth_rate_limit_max_attempts,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )


if settings.auth_rate_limit_enabled and rate_limited_paths:

    @app.middleware("http")
    async def auth_rate_limit_middleware(request: Request, call_next):
        if request.method.upper() == "POST" and request.url.path in rate_limited_paths:
            key = f"{request.url.path}:{get_request_ip(request)}"
            decision = auth_rate_limiter.allow(key)
            if not decision.allowed:
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please try again later."},
                    headers={"Retry-After": str(decision.retry_after_seconds)},
                )
                _apply_cors_headers(request, response, expose_retry_after=True)
                return response
        return await call_next(request)


@app.middleware("http")
async def csrf_protection_middleware(request: Request, call_next):
    method = request.method.upper()
    path = request.url.path
    if method in csrf_safe_methods or path in csrf_exempt_paths:
        return await call_next(request)

    session_cookie = request.cookies.get(settings.auth_cookie_name)
    if session_cookie:
        csrf_cookie = request.cookies.get(settings.auth_csrf_cookie_name)
        csrf_header = request.headers.get(settings.auth_csrf_header_name)
        if (
            not csrf_cookie
            or not csrf_header
            or not hmac.compare_digest(csrf_cookie, csrf_header)
        ):
            response = JSONResponse(
                status_code=403,
                content={"detail": "CSRF token missing or invalid"},
            )
            _apply_cors_headers(request, response)
            return response

    return await call_next(request)

app.include_router(auth_router)
app.include_router(ingest_router)
app.include_router(learning_router)
app.include_router(witnesses_router)
app.include_router(exhibits_router)
app.include_router(uploads_router)
app.include_router(matters_router)
app.include_router(documents_router)
app.include_router(search_router)
app.include_router(ontology_router)
app.include_router(agent_router)
app.include_router(admin_caselaw_router)


@app.get("/healthz")
def healthcheck() -> dict:
    return {"status": "ok"}


@app.get("/health")
def healthcheck_compat() -> dict:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict:
    return {"app": settings.app_name, "version": settings.app_version}
