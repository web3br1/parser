from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    workspace_storage_bucket: str = "context-builder-private"
    redis_url: str = "redis://localhost:6379/0"

    app_env: str = "development"
    log_level: str = "INFO"
    cors_allowed_origins: list[str] = []
    trusted_hosts: list[str] = ["*"]
    max_request_body_bytes: int = 10 * 1024 * 1024
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    rate_limit_default_requests: int = 300
    rate_limit_query_requests: int = 30
    rate_limit_upload_requests: int = 100
    rate_limit_workspace_create_requests: int = 20
    rate_limit_privacy_requests: int = 10
    rate_limit_review_mutation_requests: int = 120

    max_file_size_bytes: int = 100 * 1024 * 1024
    allowed_mime_types: list[str] = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/csv",
        "text/plain",
    ]

    query_model: str = ""
    query_model_provider: str = ""
    query_model_context_limit_tokens: int = 128000
    query_context_budget_tokens: int = 6000
    query_max_output_tokens: int = 700
    query_safety_margin_tokens: int = 1000
    query_max_candidate_facts: int = 80
    query_max_candidate_rules: int = 40
    query_enable_llm_condensation: bool = False
    query_enable_llm_answer: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
