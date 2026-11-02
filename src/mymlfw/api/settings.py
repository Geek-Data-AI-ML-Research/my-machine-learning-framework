"""API settings for Compose / local."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MYMLFW_", extra="ignore")

    env: str = "dev"
    api_version: str = "0.1.0"
    mongo_uri: str = "mongodb://127.0.0.1:27017/?replicaSet=rs0&directConnection=true"
    mongo_db: str = "mymlfw"
    redis_url: str = "redis://127.0.0.1:6379/0"
    session_secret: str = "dev-only-change-me"
    github_client_id: str = ""
    github_client_secret: str = ""
    github_oauth_stub: bool = True
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    minio_endpoint: str = "http://127.0.0.1:9000"
    minio_bucket: str = "mymlfw"
    minio_access_key: str = "mymlfw"
    minio_secret_key: str = "mymlfwsecret"
    minio_region: str = "us-east-1"


def get_settings() -> Settings:
    return Settings()
