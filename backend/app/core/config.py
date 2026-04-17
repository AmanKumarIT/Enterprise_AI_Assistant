from typing import Any, Dict, Optional, List, Union
from pydantic import PostgresDsn, field_validator, AnyHttpUrl, validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_core.core_schema import ValidationInfo

class Settings(BaseSettings):
    PROJECT_NAME: str = "Enterprise Knowledge Assistant"
    API_V1_STR: str = "/api/v1"
    
    # SECURITY WARNING: keep the secret key used in production secret!
    SECRET_KEY: str = "your-supper-secret-key-that-should-be-changed"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    BACKEND_CORS_ORIGINS: List[AnyHttpUrl] = []
    
    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)
    
    # POSTGRES
    POSTGRES_SERVER: Optional[str] = "localhost"
    POSTGRES_USER: Optional[str] = "postgres"
    POSTGRES_PASSWORD: Optional[str] = "postgres"
    POSTGRES_DB: Optional[str] = "eka_db"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: Optional[str] = None
    DB_USE_SSL: bool = False
    SQLALCHEMY_DATABASE_URI: Optional[str] = None

    @field_validator("SQLALCHEMY_DATABASE_URI", mode="before")
    def assemble_db_connection(cls, v: Optional[str], info: ValidationInfo) -> Any:
        if isinstance(v, str) and v:
            return v
        values = info.data
        
        db_url = values.get("DATABASE_URL")
        if db_url:
            if db_url.startswith("postgres://"):
                return db_url.replace("postgres://", "postgresql+asyncpg://", 1)
            elif db_url.startswith("postgresql://"):
                return db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return db_url
            
        # If any of the essential components are missing, return None
        if not all([values.get("POSTGRES_USER"), values.get("POSTGRES_SERVER")]):
            return None

        # Handle potential pydantic validation errors by wrapping in a safe build
        try:
            return PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=values.get("POSTGRES_USER"),
                password=values.get("POSTGRES_PASSWORD"),
                host=values.get("POSTGRES_SERVER"),
                port=values.get("POSTGRES_PORT", 5432),
                path=f"{values.get('POSTGRES_DB', '')}",
            ).unicode_string()
        except Exception:
            return None

    # REDIS
    REDIS_URL: str = "redis://localhost:6379/0"

    # QDRANT
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_URL: Optional[str] = None
    QDRANT_API_KEY: Optional[str] = None

    # LLM
    LLM_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    LLM_MODEL: str = "llama3-70b-8192"
    LLM_BASE_URL: Optional[str] = "https://api.groq.com/openai/v1"

    # EMBEDDING
    EMBEDDING_PROVIDER: str = "sentence_transformer"
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    HUGGINGFACE_API_KEY: str = ""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True, extra="ignore")

settings = Settings()
