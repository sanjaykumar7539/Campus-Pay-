from decimal import Decimal

import pytest

from shared import campus_units as cu


def test_one_rupee_is_one_campus_unit():
    assert cu.CU_PER_RUPEE == 1
    assert cu.rupees_to_cu(1000) == 1000
    assert cu.rupees_to_cu(Decimal("60.00")) == 60


def test_fractional_units_are_refused_not_rounded():
    with pytest.raises(cu.CampusUnitError):
        cu.rupees_to_cu(Decimal("12.50"))


def test_legacy_paise_conversion_is_exact_or_refused():
    assert cu.legacy_paise_to_cu(50000) == 500
    assert cu.legacy_paise_to_cu(500) == 5
    with pytest.raises(cu.CampusUnitError):
        cu.legacy_paise_to_cu(12345)
    assert cu.cu_to_legacy_paise(60) == 6000


@pytest.mark.parametrize("bad", [0, -1, 1.5, True, "10", cu.MAX_CU + 1])
def test_validate_cu_rejects_non_positive_non_integer_and_out_of_range(bad):
    with pytest.raises(cu.CampusUnitError):
        cu.validate_cu(bad)


def test_validate_cu_allows_zero_when_asked():
    assert cu.validate_cu(0, allow_zero=True) == 0


def test_format():
    assert cu.format_cu(1010) == "1,010 CU"
