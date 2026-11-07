from getsinapi.domain import CompositionStatus, EncargoMode, PriceStatus, Regime


def test_social_charge_mode_is_separate_from_desoneration_regime():
    assert EncargoMode.COM_ENCARGOS.value == "com_encargos"
    assert EncargoMode.SEM_ENCARGOS.value == "sem_encargos"
    assert Regime.DESONERADO != EncargoMode.SEM_ENCARGOS


def test_composition_status_preserves_source_classification():
    assert {status.value for status in CompositionStatus} == {
        "com_custo",
        "com_preco",
        "sem_custo",
        "sem_preco",
        "em_estudo",
    }


def test_price_status_remains_an_independent_concept():
    assert PriceStatus.REPORTED.value == "reported"
    assert PriceStatus.MISSING.value == "missing"
