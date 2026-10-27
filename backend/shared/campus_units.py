"""Campus Unit semantics (Campus Operating Model v0.2 §3.1, §6.1).

    ₹1 = 1 Campus Unit          (APPROVED financial concept)

The Campus Unit (CU) is the closed-loop value unit of CampusPay and the native
unit of the Institution Ledger, Wallet available value, Order totals, Payments
and Receipts. All new financial columns are named ``*_cu`` and hold **whole
Campus Units as integers**; there is no floating point anywhere in the
financial path.

Fractional Campus Units are NOT modelled in P1 (a sub-unit such as ₹12.50 is
rejected, never silently rounded). Any future precision requirement must be
introduced through an ADR (see ADR-0007).

Legacy note: the MVP stored money in paise (``*_minor`` columns). The only code
that ever converts from paise is `legacy_paise_to_cu`, used by the P1 data
migration and by the deprecated manual-payment compatibility endpoint. A Campus
Unit is NOT a paise, and no `*_minor` column exists after the P1 migration.
"""
from decimal import Decimal, InvalidOperation

CU_PER_RUPEE = 1
LEGACY_PAISE_PER_RUPEE = 100

# Guard rail against absurd values overflowing BIGINT (2**63-1); a technical
# bound, not a business limit.
MAX_CU = 10**12


class CampusUnitError(ValueError):
    """Raised for values that cannot be represented as whole Campus Units."""


def validate_cu(value: int, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CampusUnitError("Campus Units must be an integer")
    if value < 0 or (value == 0 and not allow_zero):
        raise CampusUnitError("Campus Units must be positive")
    if value > MAX_CU:
        raise CampusUnitError("Campus Units value out of range")
    return value


def rupees_to_cu(rupees: Decimal | int | str) -> int:
    """₹ → CU. Only whole-rupee amounts are representable."""
    try:
        d = Decimal(str(rupees))
    except InvalidOperation as exc:  # pragma: no cover - defensive
        raise CampusUnitError("Invalid rupee amount") from exc
    if d != d.to_integral_value():
        raise CampusUnitError("Fractional Campus Units are not supported")
    return validate_cu(int(d) * CU_PER_RUPEE, allow_zero=True)


def legacy_paise_to_cu(paise: int) -> int:
    """MVP paise → CU. Refuses (never rounds) a non-whole-rupee amount."""
    if paise % LEGACY_PAISE_PER_RUPEE != 0:
        raise CampusUnitError(
            f"{paise} paise is not a whole number of Campus Units; refusing to round"
        )
    return (paise // LEGACY_PAISE_PER_RUPEE) * CU_PER_RUPEE


def cu_to_legacy_paise(cu: int) -> int:
    """CU → MVP paise (only for the deprecated compatibility response fields)."""
    return cu * LEGACY_PAISE_PER_RUPEE // CU_PER_RUPEE


def format_cu(cu: int) -> str:
    return f"{cu:,} CU"
