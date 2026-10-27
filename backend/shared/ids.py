"""Identifier helpers. Primary keys are UUID strings (docs/DATABASE.md §3)."""
import secrets
import uuid


def new_id() -> str:
    return str(uuid.uuid4())


_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def opaque_reference(prefix: str, length: int = 10) -> str:
    """Opaque, non-semantic human-readable reference (e.g. ``ORD-K3M9X2QW7A``).

    The business format of order/receipt references is an OPEN decision; this
    is a provisional technical placeholder that carries no meaning and no
    ordering guarantee.
    """
    body = "".join(secrets.choice(_REF_ALPHABET) for _ in range(length))
    return f"{prefix}-{body}"
