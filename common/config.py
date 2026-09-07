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
    gemini_criteria_model: str = "gemini-flash-lite-latest"
    gemini_embedding_model: str = "models/gemini-embedding-001"

    master_config_path: str = "./master_config.json"
    output_dir: str = "./output"

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

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
