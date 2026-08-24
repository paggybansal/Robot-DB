"""Configuration. Environment variables are the source of truth.

Locally .env populates them. In CI, GitHub Secrets populate them. This code
cannot tell the difference and does not need to.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",          # absent in CI - pydantic ignores it silently
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    env: Literal["local", "dev", "test", "int", "stage", "prod"] = "local"

    # ---- database
    db_host: str = ""
    db_port: int = 1433
    db_name: str = ""
    db_user: str = ""
    db_password: SecretStr = SecretStr("")
    db_trusted: bool = False
    db_trust_cert: bool = True
    db_driver: str = "ODBC Driver 18 for SQL Server"
    db_timeout: int = 30

    # ---- business values present in the data
    client_entity: str = "HealthSpring"
    trigger_status: str = "Awaiting CAQH"
    cred_actions: list[str] = Field(
        default_factory=lambda: ["Initial Credentialing", "Recredentialing"]
    )
    service_address_type: str = "Service"
    caqh_id_type: str = "CAQH ID"

    # ---- AWS
    aws_region: str = "us-east-1"
    aws_profile: str = ""
    aws_secret_name: str = ""
    glue_status_job: str = ""
    glue_retry_job: str = ""
    retry_table: str = ""
    fallout_table: str = ""
    s3_bucket: str = ""
    bookmark_key: str = ""

    max_retry_attempts: int = 5

    @field_validator("cred_actions", mode="before")
    @classmethod
    def split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def db_configured(self) -> bool:
        if not (self.db_host and self.db_name):
            return False
        return self.db_trusted or bool(self.db_user)

    def missing(self, *names: str) -> list[str]:
        empty = []
        for name in names:
            value = getattr(self, name, None)
            if isinstance(value, SecretStr):
                value = value.get_secret_value()
            if not value:
                empty.append(name.upper())
        return empty


def _merge_secrets_manager(settings: Settings) -> Settings:
    """Optional: pull DB credentials from Secrets Manager using the current role."""
    import json

    import boto3

    client = boto3.client("secretsmanager", region_name=settings.aws_region)
    payload = json.loads(
        client.get_secret_value(SecretId=settings.aws_secret_name)["SecretString"]
    )
    overrides: dict[str, object] = {}
    if payload.get("host"):
        overrides["db_host"] = payload["host"]
    if payload.get("port"):
        overrides["db_port"] = int(payload["port"])
    if payload.get("dbname") or payload.get("database"):
        overrides["db_name"] = payload.get("dbname") or payload["database"]
    if payload.get("username"):
        overrides["db_user"] = payload["username"]
    if payload.get("password"):
        overrides["db_password"] = SecretStr(payload["password"])
    return settings.model_copy(update=overrides)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    if settings.aws_secret_name and not settings.db_password.get_secret_value():
        try:
            settings = _merge_secrets_manager(settings)
        except Exception as exc:  # noqa: BLE001
            import sys

            print(
                f"warning: could not read {settings.aws_secret_name}: "
                f"{str(exc).splitlines()[0][:120]}",
                file=sys.stderr,
            )
    return settings