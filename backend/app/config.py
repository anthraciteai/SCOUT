from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # DSIP
    dsip_base_url: str = "https://www.dodsbirsttr.mil/topics/api/public"
    dsip_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )

    # Ollama
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "gpt-oss:20b"
    ollama_fallback_model: str = "llama3.1:8b"
    ollama_timeout: float = 1200.0

    # Storage
    database_url: str = "sqlite:////data/sbir_scout.db"
    data_dir: str = "/data"

    # Server
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    # Docling
    use_docling: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
