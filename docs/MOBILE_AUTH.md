# Mobile authentication and receipt update

Only the requested mobile enrollment/authentication and receipt return behavior have changed.

## Mobile deployment

WebAuthn requires HTTPS on a real phone, a supported browser and a configured device screen lock/passkey. HTTP LAN URLs (such as http://192.168.x.x:8002) cannot access the phone authenticator. localhost works only on the device hosting the browser; a phone's localhost is not your PC.

Configure the backend before starting it behind an HTTPS reverse proxy:

```powershell
$env:CAMPUSPAY_WEBAUTHN_ORIGIN = "https://pay.your-college.example"
$env:CAMPUSPAY_WEBAUTHN_RP_ID = "pay.your-college.example"
```

Use your actual HTTPS domain, not the example. The default for local desktop testing is http://localhost:8002 and RP ID localhost. Open that exact origin. Run the existing demo launcher for local testing; it binds to loopback and does not expose the PC to phones. Use a configured deployment with HTTPS to test a real mobile device. Do not change the RP domain after enrollment; passkeys are bound to it.

The database migrates to 0006_mobile_webauthn. START_DEMO.bat runs migrations automatically and preserves existing demo balances and passwords. For configured deployments, run `python -m alembic upgrade head` from backend before starting the server. Back up your database first.

## Supervised enrollment

Before activating kiosk mode on the phone, open Admin, choose the account holder in the existing enrollment form, confirm informed consent and press Enroll with mobile sensor. Use the account holder's phone, not the administrator's own phone. The server verifies registration before storing a public key tied to that account. No fingerprint samples are read or stored. Existing revoke enrollment also revokes mobile passkeys.

## Ordering

Mobile detection selects the platform WebAuthn authenticator. Unsupported mobile devices receive an explanatory error with no charge. Desktop/kiosk devices keep the integrated reader flow. On a mobile device with kiosk station activation, Order & pay asks for the enrolled passkey; a separate Confirm payment with mobile sensor button starts the second verification using the same credential. Two successful signed responses are required before payment. Browser success flags are never trusted. Existing wallet, stock, receipt and idempotency rules remain in effect.

WebAuthn verifies the device user: the OS may offer fingerprint, face recognition or screen lock. The web app cannot guarantee two scans of the same finger, access raw fingerprints or determine which enrolled finger was used. The two physical-reader scans remain unchanged. A passkey is associated with the registered account; never enroll a shared staff phone for a student's wallet.

Receipts appear automatically after successful payment. The menu returns after 15 seconds or after Print receipt & finish / Finish without printing. Printing pauses the receipt timer. Failed/uncertain payments do not display a success receipt or start a new order automatically.

## Validation

Real server-side WebAuthn verification is exercised with signed virtual platform-authenticator credentials: registration, required user verification, challenge replay rejection, invalid signatures, wrong origins, unknown keys, revoked keys and debit-once receipt balance. Physical phone biometrics still require testing on the final HTTPS domain and target devices.
