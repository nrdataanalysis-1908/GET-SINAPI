"""Configuração centralizada e validada por variáveis de ambiente."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    log_level: str
    data_dir: Path
    raw_dir: Path
    staging_dir: Path
    processed_dir: Path
    manifest_dir: Path
    http_timeout: int
    http_max_retries: int
    http_backoff_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.getenv("GETSINAPI_DATA_DIR", "data"))
        settings = cls(
            environment=os.getenv("GETSINAPI_ENV", "development").strip().lower(),
            log_level=os.getenv("GETSINAPI_LOG_LEVEL", "INFO").strip().upper(),
            data_dir=data_dir,
            raw_dir=Path(os.getenv("GETSINAPI_RAW_DIR", str(data_dir / "raw"))),
            staging_dir=Path(os.getenv("GETSINAPI_STAGING_DIR", str(data_dir / "staging"))),
            processed_dir=Path(os.getenv("GETSINAPI_PROCESSED_DIR", str(data_dir / "processed"))),
            manifest_dir=Path(os.getenv("GETSINAPI_MANIFEST_DIR", str(data_dir / "manifests"))),
            http_timeout=int(os.getenv("GETSINAPI_HTTP_TIMEOUT", "45")),
            http_max_retries=int(os.getenv("GETSINAPI_HTTP_MAX_RETRIES", "4")),
            http_backoff_seconds=float(os.getenv("GETSINAPI_HTTP_BACKOFF_SECONDS", "2")),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.environment not in {"development", "test", "production"}:
            raise ValueError("GETSINAPI_ENV deve ser development, test ou production.")
        if self.http_timeout <= 0:
            raise ValueError("GETSINAPI_HTTP_TIMEOUT deve ser maior que zero.")
        if self.http_max_retries < 0:
            raise ValueError("GETSINAPI_HTTP_MAX_RETRIES não pode ser negativo.")
        if self.http_backoff_seconds < 0:
            raise ValueError("GETSINAPI_HTTP_BACKOFF_SECONDS não pode ser negativo.")

    def create_data_directories(self) -> None:
        for directory in (self.raw_dir, self.staging_dir, self.processed_dir, self.manifest_dir):
            directory.mkdir(parents=True, exist_ok=True)
