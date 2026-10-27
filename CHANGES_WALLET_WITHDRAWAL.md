# CampusPay update: Kiosk ID and Refund Money

- Add Money and fingerprint enrollment now accept typed Kiosk IDs and map to server student UUIDs.
- New Refund Money card in Kiosks & Fingerprints debits remaining wallet funds (cash-out / withdrawal), **not** a refund of a food payment.
- Existing full food-payment refund remains in Transactions; it **credits** original wallet.
- New admin endpoint `POST /api/v1/admin/wallets/{campus_user_id}/withdraw` requires `amount_cu`, `reference`, `reason`, `funds_returned: true`.
- Reference idempotency and ledger event `WALLET_WITHDRAWAL` are maintained. Original wallet mutation guard remains.
- Admin must verify the actual cash/bank return externally before clicking confirmation; software cannot verify a cash handover.
- **Important**: Existing SQLite deployment is suitable for single-user demo only. PostgreSQL concurrency tests and hardware acceptance still required before real-money production.
- Hardware: Morpho Android capture/match adapter remains pending official compatible SDK and physical test.
- The ZIP is based on the supplied Bangalore Integration Prep ZIP, not unseen changes on user's Ubuntu filesystem.
