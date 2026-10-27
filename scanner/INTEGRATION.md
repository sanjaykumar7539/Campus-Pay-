# Fingerprint scanner integration

## Current state

The user has not selected a scanner model. `adapter_contract.py` deliberately raises NotImplementedError at startup. `agent.py` is a real authenticated transport worker, not a scanner driver. Neither file can claim a real match until a hardware SDK adapter is implemented and validated. No browser button, student ID, PIN, image upload, or JavaScript boolean can replace the authenticated scanner result.

## Trust boundary

The native service is trusted to report actual sensor/matcher results. A compromised scanner host or stolen scanner key can forge those results; the backend cannot independently validate opaque match references. Protect the service with OS permissions, service isolation, device access controls, credential rotation, TLS, monitoring and appropriate hardware anti-spoofing capabilities. Use the scanner vendor's supported SDK and enroll/match quality requirements. Two repeated scans alone do not establish liveness or independent MFA.

For a shared kiosk with no Student ID entry, the adapter must support **1:N identification** against that institution's enrollment database. A reference must identify the same physical enrolled finger consistently across all permitted stations. A raw sensor slot number is not globally stable and must not be used without a protected mapping layer. Browser WebAuthn user verification alone does not identify arbitrary students using a shared scanner.

## Worker configuration

Set these environment variables for a protected native service account, not for browser JavaScript:

```
CAMPUSPAY_SERVER=https://pay.example.edu
CAMPUSPAY_SCANNER_TOKEN=<one-time key provisioned by an administrator>
CAMPUSPAY_SCANNER_ADAPTER=your_vendor_adapter
```

Install the selected vendor SDK, place your adapter on the service's Python import path, then run `python scanner/agent.py`. The worker requires HTTPS; only a deliberate CAMPUSPAY_SCANNER_LOCAL_TEST=true allows localhost HTTP. It rejects redirects to prevent forwarding scanner credentials elsewhere. The shipped contract fails startup rather than reporting a fake online scanner.

Implement Scanner.open(), capture(job, timeout_seconds), release(job), close(). See adapter_contract.py for signatures. The worker polls every two seconds; the API considers a scanner offline after 30 seconds without a successful poll/capture. The SDK capture must honor the 15-second timeout and must not block polling indefinitely.

## API protocol

Every native request uses X-Scanner-Token. The token is scoped to one registered institution/device, stored hashed on the server and cannot authenticate to staff APIs.

1. GET /api/v1/scanner/jobs returns pending jobs for that device. Each job has id, nonce, purpose (ENROLL or PAY), stage (1 or 2), and expires_at.
2. Perform a **fresh physical acquisition** after receiving the job. At stage 2 require the finger to be lifted and placed again. The same continuous touch must never generate two successful captures.
3. POST /api/v1/scanner/jobs/{id}/capture with JSON containing nonce, capture_id, matched, finger_ref.
4. capture_id must be a unique, durable acquisition ID (16–128 characters). Do not regenerate it for a retransmission. Stage 1 consumes its nonce and issues a new nonce for stage 2. Expired, mismatched, duplicate and cancelled scans are rejected. The authorization window is 90 seconds for both scans together.
5. finger_ref is an opaque reference (up to 128 characters), not a biometric image/template or a student-supplied identifier. On failure send matched=false. The two accepted references must be identical.

ENROLL jobs originate only from an authenticated administrator with recorded consent confirmation and a selected student. The SDK must prove the second sample matches the pending first sample and prevent duplicate enrollments under new aliases. Manage pending template rollback and orphan cleanup when enrollment expires, is cancelled, or the server rejects completion. Only the server's ENROLLED result means application enrollment succeeded.

PAY jobs begin from a server-priced cart. The first match resolves the active student and fixes the order; the second authorizes that order only. Money is debited through the existing wallet/ledger transaction. Native scanner requests never accept or submit an amount.

## Storage and operational requirements

CampusPay stores opaque references and scan events, not fingerprint images/templates. Your matcher/template store is a separate unresolved deployment component: implement encryption, restricted access, backup/restore, deletion/retention policy, device migration, enrollment audit and student support procedures there. Do not log samples, templates, secrets or match references. Lost keys are replaced through the admin portal; rotation cancels pending authorizations.

Before launch test real fingers, false accepts/rejects, damaged/wet fingers, removal detection, disconnect/reconnect, cross-station identification, duplicate enrollment, revocation, tampering, and interrupted captures. Provide a supervised non-PIN accessibility/support process for students who cannot use fingerprints. No alternate payment authorization is silently enabled in this release.
