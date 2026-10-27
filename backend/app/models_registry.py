"""Imports every module's persistence models so `Base.metadata` is complete (composition root only)."""
from modules.audit import models as _audit  # noqa: F401
from modules.auth import models as _auth  # noqa: F401
from modules.auth import kiosk_models as _kiosk  # noqa: F401
from modules.devices import models as _devices  # noqa: F401
from modules.institutions import models as _institutions  # noqa: F401
from modules.ledger import models as _ledger  # noqa: F401
from modules.merchants import models as _merchants  # noqa: F401
from modules.payments import models as _payments  # noqa: F401
from modules.users import models as _users  # noqa: F401
from modules.wallets import models as _wallets  # noqa: F401
