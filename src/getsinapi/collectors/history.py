"""Descoberta do catálogo histórico de pacotes XLSX mensais da CAIXA.

A estrutura XLSX unificada publicada a partir de 2025 contém todas as UFs.
Os relatórios até 2024 seguem o layout legado por UF e exigem parser próprio;
não devem ser declarados como cobertos por este coletor.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from curl_cffi import requests as browser_requests

from getsinapi.collectors.caixa import (
    DOWNLOAD_LINK_PATTERN,
    DOWNLOADS_PAGE_URL,
    CaixaDownloadError,
    _http_get,
    report_url,
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


def _http_head(url: str, *, timeout: int, headers: dict, session=None):
    """Consulta metadados do pacote sem transferir dezenas de megabytes."""
    if session is not None:
        return session.head(url, timeout=timeout, headers=headers, allow_redirects=True)
    return browser_requests.head(
        url, timeout=timeout, headers=headers, impersonate="chrome",
        allow_redirects=True,
    )


def _from_monthly_urls(settings: Settings, session=None) -> dict[str, str]:
    """Descobre cada publicação pelo padrão oficial de URL, validando HTTP HEAD."""
    now = datetime.now(UTC)
    current = now.year * 12 + now.month - 1
    first = 2025 * 12
    headers = {
        "Accept": "application/zip,application/octet-stream,*/*",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Referer": "https://www.caixa.gov.br/poder-publico/modernizacao-gestao/sinapi/Paginas/default.aspx",
    }
    found: dict[str, str] = {}
    for absolute_month in range(first, current + 1):
        year, zero_month = divmod(absolute_month, 12)
        reference = f"{year:04d}-{zero_month + 1:02d}"
        url = report_url(reference)
        response = None
        try:
            response = _http_head(
                url, timeout=settings.http_timeout, headers=headers, session=session
            )
            if response.status_code != 200:
                continue
            content_type = str(response.headers.get("Content-Type", "")).lower()
            if "text/html" in content_type:
                continue
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) <= 0:
                continue
            found[reference] = url
        except Exception as exc:
            log.warning("Não foi possível sondar a publicação %s por URL direta: %s", reference, exc)
        finally:
            if response is not None:
                response.close()
    log.info(
        "Sondagem mensal direta da CAIXA: %s competências XLSX identificadas entre 2025-01 e %s.",
        len(found), f"{now.year:04d}-{now.month:02d}",
    )
    return found


def _from_sharepoint(settings: Settings, session=None) -> dict[str, str]:
    endpoint = (
        "https://www.caixa.gov.br/_api/web/lists/getbytitle('Downloads')/Items"
        "?$select=Title,FileLeafRef,EncodedAbsUrl,FSObjType&$top=5000"
    )
    headers = {
        "Accept": "application/json;odata=verbose",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Referer": "https://www.caixa.gov.br/",
    }
    found: dict[str, str] = {}
    items_seen = 0
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
            items_seen += len(items)
            for item in items:
                filename = str(item.get("FileLeafRef") or item.get("Title") or "")
                if "SINAPI" not in filename.upper() or not filename.lower().endswith(".zip"):
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
    log.info(
        "Índice SharePoint consultado: %s itens examinados, %s competências XLSX identificadas.",
        items_seen, len(found),
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

    # A página pública de Downloads é a fonte primária. O índice SharePoint
    # complementa o catálogo, mas não pode invalidar links oficiais já extraídos
    # do HTML quando a API interna da CAIXA estiver indisponível ou incompatível.
    try:
        sharepoint_catalog = _from_sharepoint(config, session=session)
    except Exception as exc:
        if not catalog:
            raise CaixaDownloadError(
                "Não foi possível obter competências no catálogo HTML nem validar "
                f"o índice SharePoint oficial da CAIXA: {exc}"
            ) from exc
        log.warning(
            "Índice SharePoint indisponível (%s); mantendo %s competências "
            "obtidas diretamente da página oficial de Downloads.",
            exc, len(catalog),
        )
        sharepoint_catalog = {}

    catalog.update(sharepoint_catalog)

    # A listagem do portal pode ser renderizada dinamicamente e o índice
    # SharePoint pode não expor todos os itens. A URL mensal oficial é sondada
    # competência a competência; somente HTTP 200 com resposta não-HTML entra
    # no inventário. O download completo e a validação ZIP ocorrem na ingestão.
    monthly_catalog = _from_monthly_urls(config, session=session)
    catalog.update(monthly_catalog)

    if not catalog:
        raise CaixaDownloadError(
            "Nenhuma competência XLSX unificada foi encontrada nas fontes oficiais. "
            "A ingestão histórica não será marcada como concluída."
        )
    return dict(sorted(catalog.items()))
