# Kiosk hardware integration status — 8 October 2026

Status update: Android companion and paid thermal print queue now implemented; testing APK compiled, packaged and signature verified. USB/Bluetooth/LAN and 58/80mm settings are available. Actual Android runtime/printer acceptance is pending. Morpho standalone student matching is still blocked by missing MSO SDK. See docs/ANDROID_KIOSK_SETUP_TANGLISH.md for current setup.

Supplied printer archive 1744266995gjw.zip contains 2300 entries under AndroidSDK, including PosPrinterSDK.jar, an Android demo and HTML/PDF manuals. There is no Windows DLL SDK. Java methods cannot be called directly by Python or a normal web page. Do not install/run the supplied APK or unrelated drivers without verifying the vendor and model.

Selected reader: Morpho MSO 1300 E2. The download page labels packages E3, but following its Android L0 link leads to the developer-published Morpho SCL RDService Play Store listing, which explicitly lists MSO1300 E2 support for Aadhaar Auth2.0/eKYC2.1. Thus E2 Android RD support is documented; standalone campus enrollment/matching is still not established by that RD app. IDEMIA MSO SDK supports standalone template capture/matching, but no SDK headers, libraries, license or E2 sample code was supplied. UIDAI RD service encrypted PID capture is not a local 1:N student identification API. Never treat capture success, RD READY, device serial number or encrypted PID hashes as an enrolled student match.

Required inputs: kiosk operating system/version/architecture; thermal printer exact model, 58/80mm width and USB/serial/LAN connection; vendor-compatible E2 standalone SDK with license, API documentation and samples. If the kiosk is Windows, provide its printer driver/SDK or confirm its Windows print queue and documented ESC/POS support. If Android, its native printer bridge and matching SDK integration must be built for the supplied Android SDK.

Read-only diagnostic on the Windows kiosk, from the extracted CampusPay folder:

```powershell
.\.venv\Scripts\python.exe hardware\check_devices.py --rd-port 11100
```

Use the actual vendor-configured RD port. Output lists installed Windows printer queues and attempts RDService discovery. Neither is proof of printing or student matching. The tool does not capture biometrics, install drivers, print paper or debit money.

Port forwarding exposes the web app, not USB hardware. The native scanner worker and printer service must run on the computer physically connected to the devices. Keep RD/scanner services and credentials private. Phone passkeys require the exact HTTPS origin/RP ID configured on the server. Use a stable HTTPS hostname; changing the hostname after enrollment can make passkeys inaccessible.

Next-day acceptance: verify installed driver/device model, real reader enrollment and same-finger second capture, failed/different-finger refusal, disconnect recovery, paid receipt with paper/out-of-paper/cancel cases, port-forward HTTPS and one-debit retries. Actual end-to-end readiness cannot be signed off until these pass on the physical kiosk.

References:
- https://www.idemia.com/fingerprint-authentication/
- https://rdservice.in/downloads/morpho-drivers
- https://uidai.gov.in/images/Aadhaar_Registered_Devices_2_0_Revision-7_of_Jan_2022.pdf

Recheck evidence: printer IMyBinder API includes ConnectUsbPort, ConnectBtPort, ConnectNetPort, Write, WriteSendData, WriteDataByUSB, PrinterIsNormal and CheckLinkedState. PosPrinterSDK.jar contains net/posprinter classes, not Morpho libraries. Android demo source and 58/80mm command documentation are present. No Morpho/fingerprint/biometric SDK files were found in the supplied printer ZIP.

Morpho Android RD listing: https://play.google.com/store/apps/details?id=com.scl.rdservice
