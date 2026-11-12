"""Coleta resiliente dos pacotes mensais XLSX publicados pela CAIXA."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path, PurePosixPath, PureWindowsPath

import requests

from getsinapi.config import Settings

REFERENCE_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
BASE_URL = (
    "https://www.caixa.gov.br/Downloads/sinapi-relatorios-mensais/"
    "SINAPI-{reference}-formato-xlsx.zip"
)
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


@dataclass(frozen=True, slots=True)
class DownloadArtifact:
    reference: str
    url: str
    path: Path
    sha256: str
    size_bytes: int
    downloaded_at: str


class CaixaDownloadError(RuntimeError):
    """Falha ao obter ou validar um pacote oficial da CAIXA."""


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".part", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        Path(temporary_name).unlink(missing_ok=True)
        raise


def report_url(reference: str) -> str:
    if not REFERENCE_PATTERN.fullmatch(reference):
        raise ValueError("Competência inválida. Informe AAAA-MM, por exemplo 2026-09.")
    return BASE_URL.format(reference=reference)


def _retry_delay(response: requests.Response | None, attempt: int, base: float) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(max(float(retry_after), 0.0), 120.0)
            except ValueError:
                pass
    return min(base * (2 ** (attempt - 1)), 60.0)


def download_monthly_xlsx(
    reference: str,
    settings: Settings | None = None,
    session: requests.Session | None = None,
) -> DownloadArtifact:
    """Baixa, valida e registra o ZIP XLSX mensal; nunca substitui um arquivo válido."""
    url = report_url(reference)
    settings = settings or Settings.from_env()
    settings.create_data_directories()
    http = session or requests.Session()
    headers = {"User-Agent": "GET-SINAPI/0.1 (+https://github.com/nrdataanalysis-1908/GET-SINAPI)"}
    response = None

    for attempt in range(1, settings.http_max_retries + 2):
        try:
            response = http.get(url, timeout=settings.http_timeout, headers=headers)
        except requests.RequestException as exc:
            if attempt > settings.http_max_retries:
                raise CaixaDownloadError(f"Falha de rede ao baixar {url}: {exc}") from exc
            time.sleep(_retry_delay(None, attempt, settings.http_backoff_seconds))
            continue

        if response.status_code == 200:
            break
        if response.status_code not in RETRYABLE_STATUS or attempt > settings.http_max_retries:
            raise CaixaDownloadError(
                f"CAIXA respondeu HTTP {response.status_code} para a competência {reference}."
            )
        time.sleep(_retry_delay(response, attempt, settings.http_backoff_seconds))

    if response is None or response.status_code != 200:
        raise CaixaDownloadError(f"Não foi possível obter a competência {reference}.")

    payload = response.content
    if not payload or not zipfile.is_zipfile(BytesIO(payload)):
        raise CaixaDownloadError(
            "A resposta não é um ZIP válido. O pacote não será salvo nem tratado como dado SINAPI."
        )

    digest = hashlib.sha256(payload).hexdigest()
    filename = f"SINAPI-{reference}-formato-xlsx-{digest[:12]}.zip"
    target = settings.raw_dir / filename
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.is_symlink():
        raise CaixaDownloadError(
            "O destino local do pacote não pode ser um link simbólico."
        )
    if target.exists():
        if not target.is_file():
            raise CaixaDownloadError(
                "O destino local do pacote não é um arquivo regular."
            )
        try:
            local_digest, local_size = _sha256_file(target)
        except OSError as exc:
            raise CaixaDownloadError(
                f"Não foi possível verificar o pacote local existente: {target}"
            ) from exc
        if local_digest != digest or local_size != len(payload):
            _atomic_write_bytes(target, payload)
    else:
        _atomic_write_bytes(target, payload)

    try:
        stored_digest, stored_size = _sha256_file(target)
    except OSError as exc:
        raise CaixaDownloadError(
            f"Não foi possível verificar o pacote armazenado: {target}"
        ) from exc
    if stored_digest != digest or stored_size != len(payload):
        raise CaixaDownloadError(
            "O pacote armazenado não corresponde ao conteúdo recebido da CAIXA."
        )

    artifact = DownloadArtifact(
        reference=reference,
        url=url,
        path=target,
        sha256=digest,
        size_bytes=len(payload),
        downloaded_at=datetime.now(UTC).isoformat(),
    )
    manifest_dir = settings.manifest_dir
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / f"{reference}-{digest[:12]}.json"
    manifest_payload = json.dumps(
        {**asdict(artifact), "path": str(target)},
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    _atomic_write_bytes(manifest_path, manifest_payload)
    return artifact


def safe_extract_zip(
    archive_path: Path,
    destination: Path,
    max_total_uncompressed_bytes: int = 2_000_000_000,
) -> list[Path]:
    """Extrai ZIP após bloquear traversal, caminhos absolutos e links simbólicos."""
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []

    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        total_size = sum(member.file_size for member in members)
        if total_size > max_total_uncompressed_bytes:
            raise CaixaDownloadError("ZIP excede o limite de extração configurado.")

        seen_paths: set[str] = set()
        for member in members:
            name = member.filename.replace("\\", "/")
            parsed = PurePosixPath(name)
            windows_path = PureWindowsPath(name)
            mode = member.external_attr >> 16
            file_type = stat.S_IFMT(mode)
            if (
                not name
                or "\x00" in name
                or any(ord(character) < 32 or ord(character) == 127 for character in name)
                or parsed.is_absolute()
                or windows_path.drive
                or windows_path.root
                or ":" in name
                or ".." in parsed.parts
                or file_type not in (0, stat.S_IFREG, stat.S_IFDIR)
            ):
                raise CaixaDownloadError(
                    f"Caminho ou tipo de arquivo inseguro no ZIP: {member.filename}"
                )
            normalized = parsed.as_posix().rstrip("/").casefold()
            if not normalized or normalized == ".":
                raise CaixaDownloadError(
                    f"Caminho inseguro encontrado no ZIP: {member.filename}"
                )
            if normalized in seen_paths:
                raise CaixaDownloadError(
                    f"Entrada duplicada no ZIP: {member.filename}"
                )
            seen_paths.add(normalized)
            target = (destination / Path(*parsed.parts)).resolve()
            if target != destination and destination not in target.parents:
                raise CaixaDownloadError(f"Destino de extração inválido: {member.filename}")

        for member in members:
            member_mode = member.external_attr >> 16
            if member.is_dir() or stat.S_IFMT(member_mode) == stat.S_IFDIR:
                continue
            target = (
                destination / Path(*PurePosixPath(member.filename.replace("\\", "/")).parts)
            ).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
            extracted.append(target)

    return extracted
