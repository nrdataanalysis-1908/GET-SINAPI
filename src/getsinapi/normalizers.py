
"""Normalização conservadora de valores e observações de preço SINAPI."""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

from getsinapi.domain import PriceStatus


def _normalize_text(value: Any) -> str:
    """Normaliza texto para comparação, preservando o conteúdo semântico."""
    text = str(value).strip().casefold()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char for char in text
        if not unicodedata.combining(char)
    )
    return re.sub(r"\s+", " ", text)


_NOT_RESEARCHED = re.compile(
    r"\b(?:"
    r"nao pesquisad[oa]s?"
    r"|sem pesquisa de preco"
    r"|preco nao pesquisad[oa]"
    r")\b",
    flags=re.IGNORECASE,
)


def parse_decimal(value: Any) -> Decimal | None:
    """Converte valores numéricos sem arredondamento; vazio permanece None.

    Aceita Decimal, inteiros, floats e strings numéricas brasileiras.
    Não interpreta textos de ausência como zero.
    """
    if value is None:
        return None

    if isinstance(value, bool):
        raise TypeError("Booleano não é um valor monetário válido.")

    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, float):
        result = Decimal(str(value))
    else:
        raw = str(value).strip()

        if not raw:
            return None

        raw = raw.replace("R$", "").replace(" ", "")

        if "," in raw and "." in raw:
            if raw.rfind(",") > raw.rfind("."):
                raw = raw.replace(".", "").replace(",", ".")
            else:
                raw = raw.replace(",", "")
        elif "," in raw:
            raw = raw.replace(".", "").replace(",", ".")

        try:
            result = Decimal(raw)
        except InvalidOperation as exc:
            raise ValueError(
                f"Valor numérico inválido: {value!r}"
            ) from exc

    if not result.is_finite():
        raise ValueError(
            f"Valor numérico não finito: {value!r}"
        )

    return result


def classify_price(
    value: Any,
    source_status: Any = None,
) -> tuple[Decimal | None, PriceStatus]:
    """Classifica preços preservando as distinções da fonte.

    - NOT_RESEARCHED: indicação textual explícita da fonte.
    - MISSING: valor ausente ou célula vazia.
    - REPORTED_ZERO: preço numérico igual a zero.
    - REPORTED: preço numérico diferente de zero.

    A ausência de informação nunca é convertida automaticamente em zero.
    """
    status_text = (
        ""
        if source_status is None
        else _normalize_text(source_status)
    )

    if _NOT_RESEARCHED.search(status_text):
        return None, PriceStatus.NOT_RESEARCHED

    parsed = parse_decimal(value)

    if parsed is None:
        return None, PriceStatus.MISSING

    if parsed == Decimal(0):
        return parsed, PriceStatus.REPORTED_ZERO

    return parsed, PriceStatus.REPORTED
