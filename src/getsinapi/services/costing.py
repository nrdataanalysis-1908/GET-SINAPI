"""Cálculo recursivo de composições e orçamentos com precisão decimal.

A lógica reaproveita o conceito de composição recursiva do PulseSINAPI, mas
não converte preço ausente em zero e detecta ciclos na árvore de dependências.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from getsinapi.domain import EncargoMode, Regime
from getsinapi.extractors.compositions import (
    CompositionItemRecord,
    CompositionRecord,
)
from getsinapi.extractors.price_tables import InputPriceRecord


class CostStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    CYCLE = "cycle"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class CostLine:
    item_code: str
    item_type: str
    description: str
    unit: str
    coefficient: Decimal
    unit_price: Decimal | None
    total: Decimal | None
    status: CostStatus
    children: tuple[CostLine, ...] = ()


@dataclass(frozen=True, slots=True)
class CompositionCost:
    composition_code: str
    reference: str
    uf: str
    regime: Regime | None
    encargo_mode: EncargoMode
    total: Decimal | None
    status: CostStatus
    lines: tuple[CostLine, ...]
    issues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BudgetItem:
    code: str
    item_type: str
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class BudgetLine:
    code: str
    item_type: str
    quantity: Decimal
    unit_cost: Decimal | None
    total: Decimal | None
    status: CostStatus


@dataclass(frozen=True, slots=True)
class BudgetResult:
    reference: str
    uf: str
    regime: Regime | None
    encargo_mode: EncargoMode
    total: Decimal | None
    status: CostStatus
    lines: tuple[BudgetLine, ...]
    issues: tuple[str, ...]


class CompositionCostCalculator:
    """Calcula custos a partir de registros normalizados e rastreáveis."""

    def __init__(
        self,
        *,
        prices: Iterable[InputPriceRecord],
        compositions: Iterable[CompositionRecord],
        composition_items: Iterable[CompositionItemRecord],
        reference: str,
        uf: str,
        regime: Regime | None,
        encargo_mode: EncargoMode,
    ) -> None:
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", reference):
            raise ValueError("Competência inválida. Informe AAAA-MM.")
        normalized_uf = uf.strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", normalized_uf):
            raise ValueError("UF inválida. Informe uma sigla de duas letras.")

        self.reference = reference
        self.uf = normalized_uf
        self.regime = regime
        self.encargo_mode = encargo_mode
        self.compositions: dict[str, CompositionRecord] = {}
        for record in compositions:
            if record.reference != reference:
                continue
            if record.code in self.compositions:
                raise ValueError(f"Composição duplicada na competência {reference}: {record.code}.")
            self.compositions[record.code] = record
        self.items: dict[str, list[CompositionItemRecord]] = {}
        for item in composition_items:
            if item.reference != reference:
                continue
            self.items.setdefault(item.composition_code, []).append(item)

        self.prices: dict[str, InputPriceRecord] = {}
        for price in prices:
            if (
                price.reference != reference
                or price.uf != normalized_uf
                or price.regime != regime
                or price.encargo_mode != encargo_mode
            ):
                continue
            if price.code in self.prices:
                raise ValueError(
                    f"Preço duplicado para insumo {price.code}, {normalized_uf}, {reference}."
                )
            self.prices[price.code] = price

    def calculate_composition(self, composition_code: str) -> CompositionCost:
        """Calcula uma composição e expõe a árvore de componentes."""
        lines, total, status, issues = self._calculate(composition_code, ())
        return CompositionCost(
            composition_code=composition_code,
            reference=self.reference,
            uf=self.uf,
            regime=self.regime,
            encargo_mode=self.encargo_mode,
            total=total,
            status=status,
            lines=lines,
            issues=issues,
        )

    def _calculate(
        self,
        composition_code: str,
        stack: tuple[str, ...],
    ) -> tuple[tuple[CostLine, ...], Decimal | None, CostStatus, tuple[str, ...]]:
        if composition_code in stack:
            cycle = " -> ".join((*stack, composition_code))
            return (), None, CostStatus.CYCLE, (f"Ciclo de composição detectado: {cycle}.",)

        composition = self.compositions.get(composition_code)
        if composition is None:
            return (), None, CostStatus.NOT_FOUND, (
                f"Composição não encontrada: {composition_code}.",
            )

        component_records = self.items.get(composition_code, [])
        if not component_records:
            return (), None, CostStatus.INCOMPLETE, (
                f"Composição sem componentes: {composition_code}.",
            )

        next_stack = (*stack, composition_code)
        lines: list[CostLine] = []
        issues: list[str] = []
        subtotal = Decimal(0)
        complete = True
        cycle_detected = False

        for item in component_records:
            if item.item_type == "INSUMO":
                price_record = self.prices.get(item.item_code)
                if price_record is None or price_record.price is None:
                    price_status = (
                        price_record.status.value if price_record is not None else "not_found"
                    )
                    issues.append(
                        f"Preço indisponível para insumo {item.item_code} "
                        f"({price_status}) na UF {self.uf}."
                    )
                    lines.append(CostLine(
                        item_code=item.item_code,
                        item_type=item.item_type,
                        description=item.description,
                        unit=item.unit,
                        coefficient=item.coefficient,
                        unit_price=None,
                        total=None,
                        status=CostStatus.INCOMPLETE,
                    ))
                    complete = False
                    continue

                line_total = item.coefficient * price_record.price
                subtotal += line_total
                lines.append(CostLine(
                    item_code=item.item_code,
                    item_type=item.item_type,
                    description=item.description,
                    unit=item.unit,
                    coefficient=item.coefficient,
                    unit_price=price_record.price,
                    total=line_total,
                    status=CostStatus.COMPLETE,
                ))
                continue

            if item.item_type == "COMPOSICAO":
                child_lines, child_total, child_status, child_issues = self._calculate(
                    item.item_code, next_stack
                )
                issues.extend(child_issues)
                if child_status == CostStatus.CYCLE:
                    cycle_detected = True
                if child_total is None:
                    complete = False
                    lines.append(CostLine(
                        item_code=item.item_code,
                        item_type=item.item_type,
                        description=item.description,
                        unit=item.unit,
                        coefficient=item.coefficient,
                        unit_price=None,
                        total=None,
                        status=child_status,
                        children=child_lines,
                    ))
                    continue

                line_total = item.coefficient * child_total
                subtotal += line_total
                lines.append(CostLine(
                    item_code=item.item_code,
                    item_type=item.item_type,
                    description=item.description,
                    unit=item.unit,
                    coefficient=item.coefficient,
                    unit_price=child_total,
                    total=line_total,
                    status=child_status,
                    children=child_lines,
                ))
                if child_status != CostStatus.COMPLETE:
                    complete = False
                continue

            issues.append(
                f"Tipo de componente não reconhecido: {item.item_type!r} "
                f"na composição {composition_code}."
            )
            complete = False

        if cycle_detected:
            return tuple(lines), None, CostStatus.CYCLE, tuple(issues)
        if not complete:
            return tuple(lines), None, CostStatus.INCOMPLETE, tuple(issues)
        return tuple(lines), subtotal, CostStatus.COMPLETE, tuple(issues)

    def calculate_budget(self, budget_items: Iterable[BudgetItem]) -> BudgetResult:
        """Calcula orçamento sem totalizar linhas com custo incompleto."""
        lines: list[BudgetLine] = []
        issues: list[str] = []
        subtotal = Decimal(0)
        complete = True
        cycle_detected = False

        for item in budget_items:
            if item.quantity < 0:
                raise ValueError(f"Quantidade negativa não permitida: {item.code}.")
            if item.item_type == "INSUMO":
                price = self.prices.get(item.code)
                if price is None or price.price is None:
                    lines.append(BudgetLine(
                        item.code, item.item_type, item.quantity, None, None,
                        CostStatus.INCOMPLETE,
                    ))
                    issues.append(f"Preço indisponível para insumo {item.code}.")
                    complete = False
                    continue
                line_total = item.quantity * price.price
                subtotal += line_total
                lines.append(BudgetLine(
                    item.code, item.item_type, item.quantity, price.price,
                    line_total, CostStatus.COMPLETE,
                ))
                continue

            if item.item_type == "COMPOSICAO":
                cost = self.calculate_composition(item.code)
                issues.extend(cost.issues)
                if cost.total is None:
                    lines.append(BudgetLine(
                        item.code, item.item_type, item.quantity, None, None, cost.status
                    ))
                    complete = False
                    cycle_detected = cycle_detected or cost.status == CostStatus.CYCLE
                    continue
                line_total = item.quantity * cost.total
                subtotal += line_total
                lines.append(BudgetLine(
                    item.code, item.item_type, item.quantity, cost.total,
                    line_total, cost.status,
                ))
                continue

            raise ValueError(f"Tipo de item não suportado: {item.item_type!r}.")

        status = (
            CostStatus.CYCLE if cycle_detected
            else CostStatus.COMPLETE if complete
            else CostStatus.INCOMPLETE
        )
        return BudgetResult(
            reference=self.reference,
            uf=self.uf,
            regime=self.regime,
            encargo_mode=self.encargo_mode,
            total=subtotal if complete else None,
            status=status,
            lines=tuple(lines),
            issues=tuple(issues),
        )
