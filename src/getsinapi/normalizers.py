"""Normalização conservadora de valores e observações de preço SINAPI."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from getsinapi.domain import PriceStatus


_NOT_RESEARCHED = re.compile(
    r"\b(nao pesquisad[oa]|sem pesquisa de preco|preco nao pesquisado)\b",
    flags=re.IGNORECASE,
)


def parse_decimal(value: Any) -> Decimal | None:
    """Converte números sem arredondar; vazio permanece None.

    Aceita Decimal, inteiros, floats e strings numéricas brasileiras.
    Não interpreta textos de ausência como zero.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError("Booleano não é um valor monetário válido.")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))

    raw = str(value).strip().replace("R$", "").replace(" ", "")
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"Valor numérico inválido: {value!r}") from exc


def classify_price(value: Any, source_status: Any = None) -> tuple[Decimal | None, PriceStatus]:
    """Classifica preço sem inferir indisponibilidade a partir de célula vazia.

    NOT_RESEARCHED só é atribuído quando a própria fonte fornece indicação
    textual explícita. Célula vazia recebe MISSING.
    """
    status_text = "" if source_status is None else str(source_status).strip()
    if _NOT_RESEARCHED.search(status_text):
        return None, PriceStatus.NOT_RESEARCHED

    parsed = parse_decimal(value)
    if parsed is None:
        return None, PriceStatus.MISSING
    if parsed == Decimal("0"):
        return parsed, PriceStatus.REPORTED_ZERO
    return parsed, PriceStatus.REPORTED
