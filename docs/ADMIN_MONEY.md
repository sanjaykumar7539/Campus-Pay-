# Admin Refund and Add Money

Only these two requested admin features were added.

## Add Money

Admin > Kiosks > Add Money: select the account, enter a positive whole-rupee amount (up to 1,000,000 per operation), collection/payment reference and reason. Confirm funds have actually been received and verified, then submit. This records an ADMIN_TOPUP recharge, wallet movement and audit entry atomically. The reference must identify the underlying collection; reuse the SAME reference after a connection failure. A matching retry returns the recorded result without adding money twice. Reusing it for a different account or amount is rejected. A new reference is a new credit; administrators must not invent a new reference for the same collection.

This is an authorized manual credit, not bank/payment-gateway collection. The admin must verify the external funds before crediting the wallet. The replay response shows balance immediately after the original credit, not necessarily the current balance after subsequent purchases.

## Refund

Admin > Transactions > Refund: choose an eligible completed transaction, enter its reason and confirm Issue Refund. Refunds credit the FULL original paid amount to the ORIGINAL wallet. No partial, cash, bank or gateway refund is included. Each payment can create exactly one ADMIN_REFUND ledger credit, including simultaneous/repeated submissions. Failed/uncompleted payments are rejected; inactive wallets and inconsistent wallet/ledger balances are blocked. The current selector covers the latest 300 payments, matching existing payment-list limits.

Original payment/order/receipt records are preserved. A separate refund financial event, wallet movement and audit record provide the correction history. The Refund table displays refunded status, and refunded payments disappear from the eligible selector. Refund does not restock items, undo fulfillment or change original gross collection totals.

## Access and validation

Both APIs require authenticated ADMIN and institution scoping. Merchant and unauthenticated requests are denied. All credits go through ledger-first wallet mutation and commit together; injected failures roll back financial changes. Existing demo-funding switches do not enable/disable these admin operations.

Validation: 56 backend tests passed, one PostgreSQL-dependent test skipped. Includes 15 admin money scenarios with invalid input, access/tenant isolation, idempotency, concurrency and rollback; payment/mobile/scanner regressions also passed. Five frontend kiosk regression scenarios passed and admin form rendering was verified in the browser. Production PostgreSQL concurrency acceptance remains separate.

Run from the extracted CampusPay directory: .\START_DEMO.bat. No new schema migration is needed beyond existing migrations.
