"""Descoberta do catálogo histórico de pacotes XLSX mensais da CAIXA.

A estrutura XLSX unificada publicada a partir de 2025 contém todas as UFs.
Os relatórios até 2024 seguem o layout legado por UF e exigem parser próprio;
não devem ser declarados como cobertos por este coletor.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from getsinapi.collectors.caixa import (
    DOWNLOADS_PAGE_URL,
    DOWNLOAD_LINK_PATTERN,
    CaixaDownloadError,
    _http_get,
)
from getsinapi.config import Settings

log = logging.getLogger("getsinapi.collectors.history")
LEGACY_LAYOUT_END = "2024-12"
UNIFIED_LAYOUT_START = "2025-01"


def _trusted_caixa_url(value: str, base_url: str) -> str | None:
    target = urljoin(base_url, value.strip())
    parsed = urlparse(target)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        host == "caixa.gov.br" or host.endswith(".caixa.gov.br")
    ):
        return None
    return target


def _reference_from_filename(filename: str) -> str | None:
    match = DOWNLOAD_LINK_PATTERN.search(filename)
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}"


def _from_html(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, str] = {}
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        label = f"{anchor.get_text(' ', strip=True)} {href}"
        reference = _reference_from_filename(label)
        if not reference or reference < UNIFIED_LAYOUT_START:
            continue
        target = _trusted_caixa_url(href, DOWNLOADS_PAGE_URL)
        if target and "formato-xlsx" in target.lower():
            found[reference] = target
    return found


def _from_sharepoint(settings: Settings, session=None) -> dict[str, str]:
    endpoint = (
        "https://www.caixa.gov.br/_api/web/lists/getbytitle('Downloads')/Items"
        "?$select=Title,FileLeafRef,EncodedAbsUrl&$filter=FSObjType%20eq%200"
        "%20and%20substringof('SINAPI',FileLeafRef)&$top=5000"
    )
    headers = {
        "Accept": "application/json;odata=verbose",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Referer": "https://www.caixa.gov.br/",
    }
    found: dict[str, str] = {}
    next_url: str | None = endpoint
    pages = 0
    while next_url and pages < 20:
        response = _http_get(
            next_url, timeout=settings.http_timeout, headers=headers, session=session
        )
        try:
            if response.status_code != 200:
                raise CaixaDownloadError(
                    "Índice SharePoint da CAIXA indisponível "
                    f"(HTTP {response.status_code}) durante descoberta histórica."
                )
            payload = response.json()
            data = payload.get("d", payload)
            items = data.get("results", data.get("value", []))
            for item in items:
                filename = str(item.get("FileLeafRef") or item.get("Title") or "")
                if not filename.lower().endswith(".zip"):
                    continue
                reference = _reference_from_filename(filename)
                target = str(item.get("EncodedAbsUrl") or "")
                if not reference or reference < UNIFIED_LAYOUT_START:
                    continue
                trusted = _trusted_caixa_url(target, "https://www.caixa.gov.br/")
                if trusted and "formato-xlsx" in trusted.lower():
                    found[reference] = trusted
            next_url = data.get("__next") or payload.get("@odata.nextLink")
            if next_url:
                next_url = urljoin("https://www.caixa.gov.br", next_url)
            pages += 1
        finally:
            response.close()
    if next_url:
        raise CaixaDownloadError(
            "Catálogo histórico da CAIXA excedeu o limite de paginação; "
            "a descoberta foi interrompida para não declarar cobertura parcial como completa."
        )
    return found


def discover_historical_xlsx_catalog(
    settings: Settings | None = None,
    session=None,
) -> dict[str, str]:
    """Retorna o inventário consolidado das competências XLSX publicadas pela CAIXA.

    O catálogo HTML e o índice SharePoint são consultados como superfícies
    complementares. Se o índice secundário falhar, a descoberta é considerada
    inconclusiva: não se inicia uma ingestão que possa aparentar cobertura integral.
    """
    config = settings or Settings.from_env()
    response = None
    try:
        response = _http_get(
            DOWNLOADS_PAGE_URL,
            timeout=config.http_timeout,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                "Referer": "https://www.caixa.gov.br/",
            },
            session=session,
        )
        if response.status_code == 200:
            catalog = _from_html(response.text)
        else:
            log.warning(
                "Catálogo HTML da CAIXA indisponível (HTTP %s); "
                "tentando o índice SharePoint oficial.",
                response.status_code,
            )
            catalog = {}
    except Exception as exc:
        raise CaixaDownloadError(
            f"Falha ao consultar o catálogo HTML oficial da CAIXA: {exc}"
        ) from exc
    finally:
        if response is not None:
            response.close()

    try:
        sharepoint_catalog = _from_sharepoint(config, session=session)
    except Exception as exc:
        raise CaixaDownloadError(
            "Não foi possível validar o inventário histórico no índice SharePoint "
            f"oficial da CAIXA; a ingestão foi bloqueada para evitar cobertura incompleta: {exc}"
        ) from exc

    catalog.update(sharepoint_catalog)
    if not catalog:
        raise CaixaDownloadError(
            "Nenhuma competência XLSX unificada foi encontrada nas fontes oficiais. "
            "A ingestão histórica não será marcada como concluída."
        )
    return dict(sorted(catalog.items()))
