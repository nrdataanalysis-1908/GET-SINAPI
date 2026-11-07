"""Modelos de domínio para registros normalizados do SINAPI.

Os modelos preservam a diferença entre preço zero informado, preço ausente
e ausência de pesquisa explicitamente documentada pela fonte.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class Regime(StrEnum):
    DESONERADO = "desonerado"
    NAO_DESONERADO = "nao_desonerado"


class EncargoMode(StrEnum):
    """Tratamento de encargos sociais aplicado ao relatório."""

    COM_ENCARGOS = "com_encargos"
    SEM_ENCARGOS = "sem_encargos"


class CompositionStatus(StrEnum):
    """Situação da composição conforme a classificação da fonte oficial."""

    COM_CUSTO = "com_custo"
    COM_PRECO = "com_preco"
    SEM_CUSTO = "sem_custo"
    SEM_PRECO = "sem_preco"
    EM_ESTUDO = "em_estudo"


class PriceStatus(StrEnum):
    REPORTED = "reported"
    REPORTED_ZERO = "reported_zero"
    MISSING = "missing"
    NOT_RESEARCHED = "not_researched"


@dataclass(frozen=True, slots=True)
class PriceObservation:
    reference: str
    uf: str
    regime: Regime
    code: str
    description: str
    unit: str
    price: Decimal | None
    status: PriceStatus
    source_file: str
    source_sheet: str
    source_row: int

    def __post_init__(self) -> None:
        if len(self.reference) != 7 or self.reference[4] != "-":
            raise ValueError("Competência deve estar no formato AAAA-MM.")
        if len(self.uf) != 2 or not self.uf.isalpha():
            raise ValueError("UF deve conter a sigla de duas letras.")
        if not self.code.strip():
            raise ValueError("Código SINAPI não pode ser vazio.")
        if self.source_row < 1:
            raise ValueError("Linha de origem deve ser maior ou igual a 1.")
        reported = {PriceStatus.REPORTED, PriceStatus.REPORTED_ZERO}
        absent = {PriceStatus.MISSING, PriceStatus.NOT_RESEARCHED}
        if self.status in reported and self.price is None:
            raise ValueError("Preço informado exige valor numérico.")
        if self.status == PriceStatus.REPORTED_ZERO and self.price != Decimal(0):
            raise ValueError("Status reported_zero exige preço igual a zero.")
        if self.status == PriceStatus.REPORTED and self.price == Decimal(0):
            raise ValueError("Preço zero deve usar status reported_zero.")
        if self.status in absent and self.price is not None:
            raise ValueError("Preço ausente ou não pesquisado não pode conter valor.")
