from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent

# Load project .env first, then allow shell variables to override it.
load_dotenv(PROJECT_ROOT / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    value = _env(name, str(default))
    try:
        return int(value)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name, str(default)).lower()
    return value not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    grade_model: str
    provider: str = "openai"


@dataclass(frozen=True)
class RerankConfig:
    api_key: str
    model: str
    binding_host: str


@dataclass(frozen=True)
class EmbeddingConfig:
    model: str
    device: str
    dense_dim: int
    bm25_state_path: str


@dataclass(frozen=True)
class ServiceConfig:
    database_url: str
    redis_url: str
    redis_key_prefix: str
    redis_cache_ttl_seconds: int
    milvus_host: str
    milvus_port: str
    milvus_collection: str
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str


@dataclass(frozen=True)
class AppConfig:
    host: str
    port: int
    jwt_secret_key: str
    jwt_algorithm: str
    jwt_expire_minutes: int
    admin_invite_code: str
    password_pbkdf2_rounds: int


@dataclass(frozen=True)
class WeatherConfig:
    amap_api_key: str
    amap_weather_api: str


def get_llm_config() -> LLMConfig:
    api_key = _env("OPENAI_API_KEY") or _env("ARK_API_KEY")
    base_url = _env("OPENAI_BASE_URL") or _env("BASE_URL")
    model = _env("CHAT_MODEL") or _env("MODEL")
    grade_model = _env("GRADE_MODEL", model or "gpt-4.1")
    provider = _env("MODEL_PROVIDER", "openai")
    return LLMConfig(api_key=api_key, base_url=base_url, model=model, grade_model=grade_model, provider=provider)


def get_rerank_config() -> RerankConfig:
    return RerankConfig(
        api_key=_env("RERANK_API_KEY"),
        model=_env("RERANK_MODEL"),
        binding_host=_env("RERANK_BINDING_HOST") or _env("RERANK_BASE_URL"),
    )


def get_embedding_config() -> EmbeddingConfig:
    return EmbeddingConfig(
        model=_env("EMBEDDING_MODEL", "BAAI/bge-m3"),
        device=_env("EMBEDDING_DEVICE", "cpu"),
        dense_dim=_env_int("DENSE_EMBEDDING_DIM", 1024),
        bm25_state_path=_env("BM25_STATE_PATH", str(PROJECT_ROOT / "data" / "runtime" / "bm25_state.json")),
    )


def get_service_config() -> ServiceConfig:
    return ServiceConfig(
        database_url=_env("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/enterprise_customer_ops"),
        redis_url=_env("REDIS_URL", "redis://localhost:6379/0"),
        redis_key_prefix=_env("REDIS_KEY_PREFIX", "enterprise_customer_ops"),
        redis_cache_ttl_seconds=_env_int("REDIS_CACHE_TTL_SECONDS", 300),
        milvus_host=_env("MILVUS_HOST", "localhost"),
        milvus_port=_env("MILVUS_PORT", "19530"),
        milvus_collection=_env("MILVUS_COLLECTION", "enterprise_customer_ops_chunks"),
        neo4j_uri=_env("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_username=_env("NEO4J_USERNAME", "neo4j"),
        neo4j_password=_env("NEO4J_PASSWORD", "password"),
    )


def get_app_config() -> AppConfig:
    return AppConfig(
        host=_env("HOST", "0.0.0.0"),
        port=_env_int("PORT", 8000),
        jwt_secret_key=_env("JWT_SECRET_KEY", "change-this-secret"),
        jwt_algorithm=_env("JWT_ALGORITHM", "HS256"),
        jwt_expire_minutes=_env_int("JWT_EXPIRE_MINUTES", 1440),
        admin_invite_code=_env("ADMIN_INVITE_CODE"),
        password_pbkdf2_rounds=_env_int("PASSWORD_PBKDF2_ROUNDS", 310000),
    )


def get_weather_config() -> WeatherConfig:
    return WeatherConfig(
        amap_api_key=_env("AMAP_API_KEY"),
        amap_weather_api=_env("AMAP_WEATHER_API"),
    )


def auto_merge_enabled() -> bool:
    return _env_bool("AUTO_MERGE_ENABLED", True)


def auto_merge_threshold() -> int:
    return _env_int("AUTO_MERGE_THRESHOLD", 2)


def leaf_retrieve_level() -> int:
    return _env_int("LEAF_RETRIEVE_LEVEL", 3)
