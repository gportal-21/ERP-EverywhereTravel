from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://etuser:etpassword@localhost:5432/everywheretravel"
    redis_url: str = "redis://:etredispass@localhost:6379/0"
    rabbitmq_url: str = "amqp://etrabbit:etrabbitpass@localhost:5672/everywheretravel"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "etminio"
    minio_secret_key: str = "etminiopass"
    secret_key: str = "supersecretkey"
    environment: str = "development"
    anthropic_api_key: str = ""
    db_api_url: str = "http://localhost:8000"


settings = Settings()
