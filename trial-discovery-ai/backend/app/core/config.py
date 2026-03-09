from functools import lru_cache
from pathlib import Path
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_PATH, env_file_encoding="utf-8")

    app_name: str = "Acquittify Peregrine"
    app_version: str = "0.1.0"
    database_url: str | None = None
    dropbox_access_token: str | None = None
    dropbox_refresh_token: str | None = Field(default=None, alias="DROPBOX_REFRESH_TOKEN")
    dropbox_app_key: str | None = Field(default=None, alias="DROPBOX_APP_KEY")
    dropbox_app_secret: str | None = Field(default=None, alias="DROPBOX_APP_SECRET")
    dropbox_team_member_id: str | None = Field(
        default=None, alias="DROPBOX_TEAM_MEMBER_ID"
    )
    dropbox_case_root_path: str | None = Field(
        default=None, alias="DROPBOX_CASE_ROOT_PATH"
    )
    dropbox_root_path: str | None = Field(default=None, alias="DROPBOX_ROOT_PATH")
    s3_endpoint_url: str | None = Field(default=None, alias="S3_ENDPOINT_URL")
    s3_internal_endpoint_url: str | None = Field(
        default=None, alias="S3_INTERNAL_ENDPOINT_URL"
    )
    s3_access_key_id: str | None = Field(default=None, alias="S3_ACCESS_KEY_ID")
    s3_secret_access_key: str | None = Field(
        default=None, alias="S3_SECRET_ACCESS_KEY"
    )
    s3_region: str = "us-east-1"
    s3_bucket: str | None = Field(default=None, alias="MINIO_BUCKET")
    s3_secure: bool = False
    embedding_model: str = Field(default="nomic-embed-text", alias="EMBEDDING_MODEL")
    embedding_dim: int = Field(default=768, alias="EMBEDDING_DIM")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    cors_allow_origins: str | None = Field(default=None, alias="CORS_ALLOW_ORIGINS")
    llm_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "LLM_BASE_URL",
            "OPENCLAW_BASE_URL",
            "OPENAI_BASE_URL",
        ),
    )
    llm_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "LLM_API_KEY",
            "OPENCLAW_API_KEY",
        ),
    )
    llm_model: str = Field(
        default="acquittify-qwen",
        validation_alias=AliasChoices(
            "LLM_MODEL",
            "OPENCLAW_MODEL",
        ),
    )
    agent_model: str = Field(
        default="openclaw",
        validation_alias=AliasChoices(
            "AGENT_MODEL",
            "OPENCLAW_AGENT_MODEL",
        ),
    )
    openclaw_agent_id: str = Field(default="main", alias="OPENCLAW_AGENT_ID")
    llm_repair_model: str = Field(default="acquittify-qwen", alias="LLM_REPAIR_MODEL")
    embedding_base_url: str | None = Field(default=None, alias="EMBEDDING_BASE_URL")
    embedding_api_key: str | None = Field(default=None, alias="EMBEDDING_API_KEY")
    auth_secret_key: str = Field(
        default="change-this-in-production", alias="AUTH_SECRET_KEY"
    )
    auth_algorithm: str = Field(default="HS256", alias="AUTH_ALGORITHM")
    auth_access_token_exp_minutes: int = Field(
        default=60 * 12, alias="AUTH_ACCESS_TOKEN_EXP_MINUTES"
    )
    auth_cookie_name: str = Field(default="peregrine_session", alias="AUTH_COOKIE_NAME")
    auth_cookie_secure: bool = Field(default=False, alias="AUTH_COOKIE_SECURE")
    auth_cookie_samesite: str = Field(default="lax", alias="AUTH_COOKIE_SAMESITE")
    auth_cookie_domain: str | None = Field(default=None, alias="AUTH_COOKIE_DOMAIN")
    auth_csrf_cookie_name: str = Field(
        default="peregrine_csrf", alias="AUTH_CSRF_COOKIE_NAME"
    )
    auth_csrf_header_name: str = Field(
        default="X-CSRF-Token", alias="AUTH_CSRF_HEADER_NAME"
    )
    auth_password_reset_token_exp_minutes: int = Field(
        default=30, alias="AUTH_PASSWORD_RESET_TOKEN_EXP_MINUTES"
    )
    auth_password_reset_code_length: int = Field(
        default=6, alias="AUTH_PASSWORD_RESET_CODE_LENGTH"
    )
    auth_password_reset_dev_return_token: bool = Field(
        default=False, alias="AUTH_PASSWORD_RESET_DEV_RETURN_TOKEN"
    )
    auth_password_min_length: int = Field(default=12, alias="AUTH_PASSWORD_MIN_LENGTH")
    auth_password_require_upper: bool = Field(
        default=True, alias="AUTH_PASSWORD_REQUIRE_UPPER"
    )
    auth_password_require_lower: bool = Field(
        default=True, alias="AUTH_PASSWORD_REQUIRE_LOWER"
    )
    auth_password_require_number: bool = Field(
        default=True, alias="AUTH_PASSWORD_REQUIRE_NUMBER"
    )
    auth_password_require_symbol: bool = Field(
        default=True, alias="AUTH_PASSWORD_REQUIRE_SYMBOL"
    )
    auth_email_sender: str | None = Field(default=None, alias="AUTH_EMAIL_SENDER")
    auth_email_region: str | None = Field(default=None, alias="AUTH_EMAIL_REGION")
    auth_mfa_issuer: str = Field(default="Acquittify", alias="AUTH_MFA_ISSUER")
    auth_mfa_challenge_exp_minutes: int = Field(
        default=10, alias="AUTH_MFA_CHALLENGE_EXP_MINUTES"
    )
    auth_mfa_challenge_max_attempts: int = Field(
        default=5, alias="AUTH_MFA_CHALLENGE_MAX_ATTEMPTS"
    )
    auth_mfa_backup_code_count: int = Field(
        default=8, alias="AUTH_MFA_BACKUP_CODE_COUNT"
    )
    auth_rate_limit_enabled: bool = Field(default=True, alias="AUTH_RATE_LIMIT_ENABLED")
    auth_rate_limit_window_seconds: int = Field(
        default=60, alias="AUTH_RATE_LIMIT_WINDOW_SECONDS"
    )
    auth_rate_limit_max_attempts: int = Field(
        default=10, alias="AUTH_RATE_LIMIT_MAX_ATTEMPTS"
    )
    auth_rate_limit_backend: str = Field(
        default="memory", alias="AUTH_RATE_LIMIT_BACKEND"
    )
    auth_rate_limit_paths: str = Field(
        default="/auth/login,/auth/register,/auth/password/forgot,/auth/password/reset,/auth/mfa/login/verify",
        alias="AUTH_RATE_LIMIT_PATHS",
    )
    auth_admin_override_emails: str = Field(
        default="ron@ronaldwchapman.com",
        alias="AUTH_ADMIN_OVERRIDE_EMAILS",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
