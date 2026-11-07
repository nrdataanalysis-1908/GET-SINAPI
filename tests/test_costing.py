from decimal import Decimal

from getsinapi.domain import (
    CompositionStatus,
    EncargoMode,
    PriceStatus,
    Regime,
)
from getsinapi.extractors.compositions import (
    CompositionItemRecord,
    CompositionRecord,
)
from getsinapi.extractors.price_tables import InputPriceRecord
from getsinapi.services.costing import (
    BudgetItem,
    CompositionCostCalculator,
    CostStatus,
)


def composition(code):
    return CompositionRecord(
        reference="2026-09",
        code=code,
        description=f"Composição {code}",
        unit="UN",
        status=CompositionStatus.COM_CUSTO,
        source_file="SINAPI.xlsx",
        source_sheet="Analítico",
        source_row=11,
    )


def component(parent, code, item_type, coefficient):
    return CompositionItemRecord(
        reference="2026-09",
        composition_code=parent,
        item_code=code,
        item_type=item_type,
        description=f"Item {code}",
        unit="UN",
        coefficient=Decimal(coefficient),
        source_file="SINAPI.xlsx",
        source_sheet="Analítico",
        source_row=12,
    )


def price(code, value, status=PriceStatus.REPORTED):
    return InputPriceRecord(
        reference="2026-09",
        code=code,
        description=f"Insumo {code}",
        unit="UN",
        uf="MG",
        regime=Regime.NAO_DESONERADO,
        encargo_mode=EncargoMode.COM_ENCARGOS,
        price=Decimal(value) if value is not None else None,
        status=status,
        price_origin="C",
        source_file="SINAPI.xlsx",
        source_sheet="ISD",
        source_row=11,
    )


def calculator(prices, compositions, items):
    return CompositionCostCalculator(
        prices=prices,
        compositions=compositions,
        composition_items=items,
        reference="2026-09",
        uf="mg",
        regime=Regime.NAO_DESONERADO,
        encargo_mode=EncargoMode.COM_ENCARGOS,
    )


def test_calculates_nested_composition_and_budget_with_decimal_precision():
    engine = calculator(
        [price("0001", "10.00")],
        [composition("100"), composition("200")],
        [
            component("100", "200", "COMPOSICAO", "2"),
            component("200", "0001", "INSUMO", "3"),
        ],
    )

    result = engine.calculate_composition("100")
    assert result.status == CostStatus.COMPLETE
    assert result.total == Decimal("60.00")
    assert result.lines[0].unit_price == Decimal("30.00")

    budget = engine.calculate_budget([
        BudgetItem("100", "COMPOSICAO", Decimal("4"))
    ])
    assert budget.status == CostStatus.COMPLETE
    assert budget.total == Decimal("240.00")


def test_missing_price_makes_composition_total_incomplete_not_zero():
    engine = calculator(
        [price("0001", None, PriceStatus.MISSING)],
        [composition("100")],
        [component("100", "0001", "INSUMO", "3")],
    )

    result = engine.calculate_composition("100")
    assert result.status == CostStatus.INCOMPLETE
    assert result.total is None
    assert result.lines[0].total is None
    assert result.issues


def test_reported_zero_is_a_valid_zero_cost():
    engine = calculator(
        [price("0001", "0", PriceStatus.REPORTED_ZERO)],
        [composition("100")],
        [component("100", "0001", "INSUMO", "3")],
    )

    result = engine.calculate_composition("100")
    assert result.status == CostStatus.COMPLETE
    assert result.total == Decimal("0")


def test_recursive_cycle_is_detected_and_not_totaled():
    engine = calculator(
        [],
        [composition("100"), composition("200")],
        [
            component("100", "200", "COMPOSICAO", "1"),
            component("200", "100", "COMPOSICAO", "1"),
        ],
    )

    result = engine.calculate_composition("100")
    assert result.status == CostStatus.CYCLE
    assert result.total is None
    assert any("Ciclo de composição" in issue for issue in result.issues)
