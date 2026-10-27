from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.errors import ok
from core.security import require_roles, tenant_db
from core.tenancy import Principal
from modules.wallets import service
from modules.wallets.service import MovementResult

router = APIRouter(prefix="/api/v1", tags=["wallets"])


class WalletCreate(BaseModel):
    campus_user_id: str = Field(min_length=1, max_length=64)


class DemoFundingRequest(BaseModel):
    campus_user_id: str = Field(min_length=1, max_length=64)
    amount_cu: int = Field(gt=0, description="Whole Campus Units (₹1 = 1 CU)")
    reference: str = Field(min_length=1, max_length=128, description="Idempotency reference for this funding operation")


def _movement(m: MovementResult) -> dict:
    return {"wallet_id": m.wallet_id, "transaction_id": m.transaction_id, "ledger_entry_id": m.ledger_entry_id,
            "type": m.type, "amount_cu": m.amount_cu, "balance_before_cu": m.balance_before_cu,
            "balance_after_cu": m.balance_after_cu, "replayed": m.replayed}


@router.get("/wallet/me")
def my_wallet(principal: Principal = Depends(require_roles("STUDENT")), db: Session = Depends(tenant_db)):
    w = service.get_wallet(db, institution_id=principal.institution_id, campus_user_id=principal.user_id)
    return ok({"wallet_id": w.id, "campus_user_id": w.campus_user_id, "available_cu": w.available_cu, "status": w.status})


@router.get("/wallets")
def list_wallets(principal: Principal = Depends(require_roles("ADMIN")), db: Session = Depends(tenant_db)):
    return ok(service.list_wallets(db, institution_id=principal.institution_id))


@router.post("/wallets", status_code=201)
def create_wallet(body: WalletCreate, principal: Principal = Depends(require_roles("ADMIN")),
                  db: Session = Depends(tenant_db)):
    w = service.create_wallet(db, institution_id=principal.institution_id, campus_user_id=body.campus_user_id,
                              actor_id=principal.user_id, actor_role=principal.role)
    db.commit()
    return ok({"wallet_id": w.id, "campus_user_id": w.campus_user_id, "available_cu": w.available_cu, "status": w.status},
              "Wallet created")


@router.get("/wallets/{campus_user_id}/history")
def wallet_history(campus_user_id: str, limit: int = 50, principal: Principal = Depends(require_roles("ADMIN")),
                   db: Session = Depends(tenant_db)):
    return ok(service.get_history(db, institution_id=principal.institution_id, campus_user_id=campus_user_id, limit=limit))


@router.get("/wallets/{campus_user_id}/reconciliation")
def wallet_reconciliation(campus_user_id: str, principal: Principal = Depends(require_roles("ADMIN")),
                          db: Session = Depends(tenant_db)):
    return ok(service.reconcile_wallet(db, institution_id=principal.institution_id, campus_user_id=campus_user_id))


@router.post("/demo/wallet-funding")
def demo_wallet_funding(body: DemoFundingRequest, principal: Principal = Depends(require_roles("ADMIN")),
                        db: Session = Depends(tenant_db)):
    """DEMO/seed funding only. NOT the production recharge workflow (Operating Model §7, MG-03 OPEN)."""
    m = service.credit_demo_funding(db, institution_id=principal.institution_id, campus_user_id=body.campus_user_id,
                                    amount_cu=body.amount_cu, reference=body.reference,
                                    actor_id=principal.user_id, actor_role=principal.role)
    db.commit()
    return ok(_movement(m), "Demo funding applied (not a production recharge)")


from pydantic import ConfigDict
from core.errors import ForbiddenError

class AdminCredit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_cu: int = Field(gt=0, le=1000000, strict=True)
    reference: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=500)
    funds_received: bool

@router.post("/admin/wallets/{campus_user_id}/add-money")
def admin_add_money(campus_user_id: str, body: AdminCredit,
        p=Depends(require_roles("ADMIN")), db=Depends(tenant_db)):
    if not body.funds_received:
        raise ForbiddenError("Confirm funds were received before adding money")
    m = service.credit_admin(db, institution_id=p.institution_id, campus_user_id=campus_user_id,
        amount_cu=body.amount_cu, reference=body.reference, reason=body.reason, actor_id=p.user_id)
    db.commit()
    return ok(_movement(m), "Money added to wallet")



class AdminWithdrawal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount_cu: int = Field(gt=0, le=1000000, strict=True)
    reference: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=500)
    funds_returned: bool


@router.post("/admin/wallets/{campus_user_id}/withdraw")
def admin_withdraw(campus_user_id: str, body: AdminWithdrawal,
        p=Depends(require_roles("ADMIN")), db=Depends(tenant_db)):
    if not body.funds_returned:
        raise ForbiddenError("Confirm funds were returned before withdrawing from wallet")
    m = service.withdraw_admin(db, institution_id=p.institution_id, campus_user_id=campus_user_id,
        amount_cu=body.amount_cu, reference=body.reference, reason=body.reason, actor_id=p.user_id)
    db.commit()
    return ok(_movement(m), "Wallet withdrawal recorded")
