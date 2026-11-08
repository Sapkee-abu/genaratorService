from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mongodb_uri: str
    mongodb_db_name: str = "aunqa"

    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_collection: str = "evidence_chunks"

    gemini_api_key: str
    gemini_criteria_model: str = "gemini-3.8-flash"
    gemini_embedding_model: str = "models/gemini-embedding-001"

    # Query-side embedding for ChromaDB search (common/bge_embedding.py,
    # mcp_server/server.py::search_evidence). The real `document_chunks`
    # collection is embedded by the Import Service using BGE-M3 (1024-dim),
    # NOT Gemini - query vectors must come from the same model or Chroma
    # rejects the dimension mismatch outright (change.md Blocker 1). This is
    # unrelated to gemini_embedding_model above, which is unused for Chroma
    # queries now.
    bge_m3_model: str = "BAAI/bge-m3"

    master_config_path: str = "./master_config.json"
    output_dir: str = "./output"

    # Template Service HTTP API (common/template_client.py) - the real SAR
    # Template file (template_ps) lives on a different machine's filesystem
    # than this Generator Service instance can read directly, so it's
    # fetched via GET {template_service_url}/api/templates/{version}/download
    # instead of local disk (change.md Blocker 2). Leaving this unset means
    # get_sar_template() correctly reports "not found" rather than silently
    # falling back to a stale/local template - no code change needed to
    # point this at the real service later, only .env.
    template_service_url: str | None = None
    template_service_timeout_seconds: float = 15.0

    evidence_top_k: int = 6

    rapidfuzz_threshold: int = 80
    semantic_similarity_threshold: float = 0.45
    sentence_transformer_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    max_verification_retries: int = 3

    # Testing only, toggled purely via .env - no code change needed to turn
    # on/off. When a criterion's guideline/required_evidence are empty (as
    # PS's currently are, pending real มคอ.2/appointment-order Evidence),
    # the Criteria Agent tends to default to reporting every target slot as
    # "missing" and writing nothing, rather than describing what IS present
    # in Evidence - this nudges it to do the latter instead, purely for
    # seeing pipeline output while real Evidence is still incomplete.
    # Irrelevant once a criterion's guideline/required_evidence are restored
    # to real values (nothing left to be "empty" about) - turn it back to
    # false at that point for cleanliness, but it's harmless either way.
    test_mode_force_content: bool = False

    # api_server.py only - CORS origin(s) allowed to call it (the Import
    # Service frontend's "Generate SAR" page).
    cors_origins: str = "http://localhost:5173"

    # Monitor Service integration (monitor/client.py). Real, confirmed
    # contract: GET {monitor_service_url}{monitor_readiness_path} ->
    # {"generatedReady": true|false} (change.md "Fix and align Generator
    # Service with the real Monitor Readiness Contract" sec.4).
    # `monitor_readiness_path` is a template - MonitorClient fills in
    # {curriculum_id} - so the hostname/base path stay pure .env
    # configuration, never hardcoded. Leaving `monitor_service_url` unset
    # means MonitorClient.check_readiness() always returns
    # MONITOR_UNAVAILABLE (never a fabricated READY), so `/api/generate`
    # correctly stops generation until a real URL is configured. No code
    # change is needed to point this at the real Monitor later - only .env.
    monitor_service_url: str | None = None
    monitor_readiness_path: str = "/monitor/{curriculum_id}/readiness"
    monitor_timeout_seconds: float = 5.0
    # Placeholder only - NOT sent on any request yet. The real Monitor auth
    # mechanism (Bearer? API key header? none?) is unconfirmed - wiring this
    # in is future work once that contract exists, not guessed now.
    monitor_auth_token: str | None = None
    monitor_contract: str = "legacy"

    # DEVELOPMENT/TEST ONLY. When true (env GENERATOR_DEV_MODE=true) api_server.py
    # additionally serves POST /api/dev/generate, which runs the SAME real Generator
    # core as POST /api/generate but WITHOUT the Monitor READY gate. Default false:
    # a normal/production process never exposes it. Refused at startup if a real
    # Monitor is configured (monitor_service_url) - the bypass must never coexist
    # with a live production gate.
    generator_dev_mode: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
