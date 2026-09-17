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
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_fallback_model: str = "llama3.1:8b"
    ollama_timeout: float = 600.0

    # Storage
    database_url: str = "sqlite:////data/scout.db"
    data_dir: str = "/data"
    vault_dir: str = "/data/vault"

    # Org / auth (file vault + optional Keycloak / SeaweedFS)
    auth_disabled: bool = True
    auth_secret: str = "scout-dev-secret-change-me"
    default_company: str = "anthracite"
    storage_endpoint: str = ""  # empty = disk only; http://127.0.0.1:8333 for SeaweedFS
    storage_bucket: str = "scout"
    keycloak_url: str = ""  # in-cluster, e.g. http://127.0.0.1:8081
    keycloak_public_url: str = ""
    keycloak_realm: str = "scout"
    keycloak_audience: str = "scout-frontend"

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
