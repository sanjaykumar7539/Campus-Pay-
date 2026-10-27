# EGS role design integration

The uploaded EGS role mockups are translated into the P1 HTML/CSS/JavaScript frontend. The implementation uses their navy, magenta and yellow palette, sidebar navigation, card layouts, white college header and icon artwork. `frontend/demo/assets/egs-logo.svg` reuses the logo viewport and embedded source image supplied in the design SVG. It is not a traced or regenerated logo.

| Screen | Implementation | Working behavior |
| --- | --- | --- |
| Login | `login.html`, `login.js`, `login.css` | Institution + login ID + password. Admin opens admin workspace; merchant opens merchant workspace. Show/hide password, submission state and errors. |
| Account settings | `account.html`, `account.js` | Changes the authenticated admin/merchant's login ID and/or password after current-password verification. Signs out all previous sessions. |
| Admin | `admin.html`, `admin.js` | Overview cards, recent merchant collections, latest transactions; navigable student, merchant, catalog, ledger, reconciliation and audit panels. Existing operations retained. |
| Merchant | `merchant.html`, `merchant.js` | Merchant-scoped recent paid orders, search, kiosk access and fulfillment controls. Metrics are explicitly limited to the loaded recent 100 orders. |
| Ordering station | `kiosk.html`, `kiosk.css` | Existing order/PIN payment flow restyled to EGS. Admin station links pass both device and merchant so the intended catalog opens. |
| Student desktop/mobile | `student-preview.html`, `student-preview.css` | Responsive preview with sample data. Not a live student account. |
| Shared shell | `app.js`, `shell.js`, `style.css` | API client, role guard, reusable navigation, account avatar, EGS logo and SVG icons. |

## Account API

`PATCH /api/v1/auth/credentials`, authenticated as ADMIN or MERCHANT_STAFF:

```json
{
  "current_password": "<current password>",
  "username": "<new or current login ID>",
  "new_password": "<optional new password>"
}
```

Omit `new_password` to keep it. `username` is optional for API clients changing only the password. The endpoint derives the account and institution from the verified token; it accepts no target user ID. A login ID is unique inside its institution. New passwords use the existing bcrypt hashing and must be 8+ characters, at most 72 UTF-8 bytes. Passwords and tokens are not returned in audit metadata.

Migration `0003_account_settings` adds `credentials.token_version`. Updating credentials increments the version atomically. Login embeds that version in the token, and each authenticated request checks credential status, username and version against the database. Older tokens from before the migration default to version 0 and continue working until credentials change. The update response requires a fresh sign-in.

## Deliberate differences from the static mockups

The live dashboards show actual API values, not the names and financial amounts in the design images. P1 does not have settlement records, QR payment request APIs, student login or production recharge. Those are not presented as working financial controls. Admin collections are all-time totals; the merchant chart is scoped to the latest 15 payment attempts, and merchant overview cards to the latest 100 orders.

See `START_HERE_WINDOWS.md` for update and run instructions. Preserve the existing database and apply the migration before restarting the app.
