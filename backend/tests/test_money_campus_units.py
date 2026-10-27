import pytest

from shared.campus_units import (CampusUnitError, cu_to_legacy_paise, format_cu, legacy_paise_to_cu, rupees_to_cu,
                                 validate_cu)


def test_one_rupee_is_one_campus_unit():
    assert rupees_to_cu(1) == 1
    assert rupees_to_cu("60") == 60
    assert legacy_paise_to_cu(6000) == 60
    assert cu_to_legacy_paise(60) == 6000
    assert format_cu(1500) == "1,500 CU"


def test_fractional_campus_units_are_refused_never_rounded():
    with pytest.raises(CampusUnitError):
        rupees_to_cu("12.50")
    with pytest.raises(CampusUnitError):
        legacy_paise_to_cu(1250)


@pytest.mark.parametrize("bad", [0, -1, 1.5, "10", True, 10**13])
def test_validate_cu_rejects_non_integer_or_out_of_range(bad):
    with pytest.raises(CampusUnitError):
        validate_cu(bad)


def test_no_floating_point_in_financial_columns():
    from modules.ledger.models import LedgerEntry
    from modules.payments.models import Payment
    from modules.wallets.models import Wallet
    for model, cols in ((LedgerEntry, ("amount_cu", "position_after_cu")), (Wallet, ("available_cu",)), (Payment, ("amount_cu",))):
        for c in cols:
            assert type(getattr(model, c).type).__name__ == "BigInteger"
