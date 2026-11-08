"""Coleta resiliente dos pacotes mensais XLSX publicados pela CAIXA."""
from __future__ import annotations

import hashlib
import json
import re
import time
import zipfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as browser_requests

from getsinapi.config import Settings

REFERENCE_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
BASE_URL = (
    "https://www.caixa.gov.br/Downloads/sinapi-relatorios-mensais/"
    "SINAPI-{reference}-formato-xlsx.zip"
)
DOWNLOADS_PAGE_URL = "https://www.caixa.gov.br/site/paginas/downloads.aspx"
DOWNLOAD_LINK_PATTERN = re.compile(
    r"SINAPI[-_](20\d{2})[-_](0[1-9]|1[0-2])[-_ ]formato[-_ ]xlsx",
    re.IGNORECASE,
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



def _http_get(url: str, *, timeout: int, headers: dict, session=None):
    """Acessa a CAIXA com fingerprint de navegador para contornar bloqueios anti-bot."""
    if session is not None:
        return session.get(url, timeout=timeout, headers=headers)
    return browser_requests.get(
        url, timeout=timeout, headers=headers, impersonate="chrome",
        allow_redirects=True,
    )


def _discover_via_sharepoint(settings: Settings, session=None) -> tuple[str, str]:
    """Descobre pacotes mensais pelo índice SharePoint oficial quando o catálogo HTML falha."""
    endpoint = (
        "https://www.caixa.gov.br/_api/web/lists/getbytitle('Downloads')/Items"
        "?$select=Title,FileLeafRef,EncodedAbsUrl&$filter=FSObjType%20eq%200"
        "%20and%20substringof('SINAPI',FileLeafRef)&$top=5000"
    )
    headers = {
        "Accept": "application/json;odata=verbose",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Referer": "https://www.caixa.gov.br/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    candidates: dict[str, str] = {}
    next_url: str | None = endpoint
    pages = 0
    while next_url and pages < 4:
        response = None
        try:
            response = _http_get(
                next_url, timeout=settings.http_timeout, headers=headers, session=session,
            )
            if response.status_code != 200:
                raise CaixaDownloadError(
                    "Índice SharePoint oficial da CAIXA indisponível "
                    f"(HTTP {response.status_code}); nenhuma fonte alternativa validada."
                )
            payload = response.json()
            data = payload.get("d", payload)
            items = data.get("results", data.get("value", []))
            for item in items:
                filename = str(item.get("FileLeafRef") or item.get("Title") or "")
                target = str(item.get("EncodedAbsUrl") or "")
                match = DOWNLOAD_LINK_PATTERN.search(filename)
                if not match or not filename.lower().endswith(".zip") or not target:
                    continue
                reference = f"{match.group(1)}-{match.group(2)}"
                parsed = urlparse(target)
                hostname = (parsed.hostname or "").lower()
                if parsed.scheme == "https" and (
                    hostname == "caixa.gov.br" or hostname.endswith(".caixa.gov.br")
                ):
                    candidates[reference] = target
            next_url = data.get("__next") or payload.get("@odata.nextLink")
            if next_url:
                next_url = urljoin("https://www.caixa.gov.br", next_url)
            pages += 1
        except (requests.RequestException, browser_requests.RequestsError, ValueError) as exc:
            raise CaixaDownloadError(
                f"Falha ao consultar o índice SharePoint oficial da CAIXA: {exc}"
            ) from exc
        finally:
            if response is not None:
                response.close()
    if not candidates:
        raise CaixaDownloadError(
            "Catálogo HTML e índice SharePoint da CAIXA não forneceram "
            "um pacote mensal XLSX oficial identificável."
        )
    return max(candidates.items(), key=lambda item: item[0])


def discover_latest_monthly_xlsx(
    settings: Settings | None = None,
    session=None,
) -> tuple[str, str]:
    """Descobre a última competência XLSX pelos links publicados no catálogo oficial."""
    settings = settings or Settings.from_env()
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Referer": "https://www.caixa.gov.br/",
    }
    response = None
    try:
        response = _http_get(
            DOWNLOADS_PAGE_URL, timeout=settings.http_timeout,
            headers=headers, session=session,
        )
        if response.status_code != 200:
            catalog_status = response.status_code
            response.close()
            response = None
            log.warning(
                "Catálogo HTML da CAIXA indisponível (HTTP %s); tentando o índice oficial SharePoint.",
                catalog_status,
            )
            return _discover_via_sharepoint(settings=settings, session=session)
        soup = BeautifulSoup(response.text, "html.parser")
        candidates: dict[str, str] = {}
        for anchor in soup.find_all("a", href=True):
            href = str(anchor.get("href", "")).strip()
            label = f"{anchor.get_text(' ', strip=True)} {href}"
            match = DOWNLOAD_LINK_PATTERN.search(label)
            if not match:
                continue
            reference = f"{match.group(1)}-{match.group(2)}"
            target = urljoin(DOWNLOADS_PAGE_URL, href)
            parsed = urlparse(target)
            hostname = (parsed.hostname or "").lower()
            if parsed.scheme != "https" or not (
                hostname == "caixa.gov.br" or hostname.endswith(".caixa.gov.br")
            ):
                continue
            candidates[reference] = target
        if not candidates:
            raise CaixaDownloadError(
                "O catálogo oficial foi acessado, mas nenhum link mensal XLSX do SINAPI "
                "foi identificado. A atualização foi interrompida sem alterar a base."
            )
        return max(candidates.items(), key=lambda item: item[0])
    except (requests.RequestException, browser_requests.RequestsError) as exc:
        raise CaixaDownloadError(
            f"Falha de rede ao consultar o catálogo oficial da CAIXA: {exc}"
        ) from exc
    finally:
        if response is not None:
            response.close()


def download_monthly_xlsx(
    reference: str,
    settings: Settings | None = None,
    session: requests.Session | None = None,
    source_url: str | None = None,
) -> DownloadArtifact:
    """Baixa, valida e registra o ZIP XLSX mensal; nunca substitui um arquivo válido."""
    url = source_url or report_url(reference)
    settings = settings or Settings.from_env()
    settings.create_data_directories()
    headers = {
        "Accept": "application/zip,application/octet-stream,*/*",
        "Referer": DOWNLOADS_PAGE_URL,
    }
    response = None

    for attempt in range(1, settings.http_max_retries + 2):
        try:
            response = _http_get(
                url, timeout=settings.http_timeout, headers=headers, session=session,
            )
        except (requests.RequestException, browser_requests.RequestsError) as exc:
            if attempt > settings.http_max_retries:
                raise CaixaDownloadError(f"Falha de rede ao baixar {url}: {exc}") from exc
            time.sleep(_retry_delay(None, attempt, settings.http_backoff_seconds))
            continue

        if response.status_code == 200:
            break
        if response.status_code not in RETRYABLE_STATUS or attempt > settings.http_max_retries:
            status = response.status_code
            response.close()
            if status == 403:
                raise CaixaDownloadError(
                    f"CAIXA negou o download da competência {reference} (HTTP 403), "
                    "mesmo após a descoberta pelo catálogo oficial. Nenhum arquivo foi aceito."
                )
            raise CaixaDownloadError(
                f"CAIXA respondeu HTTP {status} para a competência {reference}."
            )
        delay = _retry_delay(response, attempt, settings.http_backoff_seconds)
        response.close()
        time.sleep(delay)

    if response is None or response.status_code != 200:
        raise CaixaDownloadError(f"Não foi possível obter a competência {reference}.")

    payload = response.content
    response.close()
    if not payload or not zipfile.is_zipfile(BytesIO(payload)):
        raise CaixaDownloadError(
            "A resposta não é um ZIP válido. O pacote não será salvo nem tratado como dado SINAPI."
        )

    digest = hashlib.sha256(payload).hexdigest()
    filename = f"SINAPI-{reference}-formato-xlsx-{digest[:12]}.zip"
    target = settings.raw_dir / filename
    target.parent.mkdir(parents=True, exist_ok=True)

    if not target.exists():
        temporary = target.with_suffix(target.suffix + ".part")
        temporary.write_bytes(payload)
        temporary.replace(target)

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
    manifest_tmp = manifest_path.with_suffix(".json.part")
    manifest_tmp.write_text(
        json.dumps({**asdict(artifact), "path": str(target)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manifest_tmp.replace(manifest_path)
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

        for member in members:
            name = member.filename.replace("\\", "/")
            parsed = Path(name)
            mode = (member.external_attr >> 16) & 0o170000
            if parsed.is_absolute() or ".." in parsed.parts or mode == 0o120000:
                raise CaixaDownloadError(f"Caminho inseguro encontrado no ZIP: {member.filename}")
            target = (destination / parsed).resolve()
            if target != destination and destination not in target.parents:
                raise CaixaDownloadError(f"Destino de extração inválido: {member.filename}")

        for member in members:
            if member.is_dir():
                continue
            target = (destination / member.filename.replace("\\", "/")).resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as output:
                while chunk := source.read(1024 * 1024):
                    output.write(chunk)
            extracted.append(target)

    return extracted
