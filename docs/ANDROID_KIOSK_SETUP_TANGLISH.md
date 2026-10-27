# CampusPay Android kiosk setup — Tanglish

## Ippo ready aagirukkura parts

- Android companion app: supplied PosPrinterSDK.jar use pannum.
- Printer USB / paired Bluetooth / LAN connection options.
- 58mm (384 dots), 80mm (576 dots) raster receipt settings. Actual printer resolution/paper check pannanum.
- Admin printer key provisioning; printer key scanner API access kudukkaadhu.
- Paid receipt server verification, one-time job claim, restart journal, timeout/unknown delivery handling.
- Android integrated scanner mode / mobile passkey mode selection.
- Mobile activation physical kiosk session-ai revoke pannaadhu; phone checkout scanner queue-ai block pannaadhu.
- Admin Refund / Add Money, menu, images, receipt balance, existing scanner and mobile authentication preserve aagiyirukku.

## Mukkiyamaana remaining limitation

Morpho MSO 1300 E2-ku Android RD app support irukku. Aana college student enrollment + local identification-ku standalone MSO matching SDK adapter innum supply pannala. Indha app RD presence/USB details mattum diagnose pannum; RD capture or encrypted PID-ai student identity proof-ah accept pannaadhu. MorphO matching driver complete aagara varaikkum integrated fingerprint payment offline/fail-closed-a irukkum. Fake fingerprint success/PIN bypass illa.

Printer transport support develop panniyirukkom; endha printer modelum guaranteed nu artham illa. Supplied POS SDK + raster ESC/POS support irukkura printer-la real paper acceptance test venum. Cutter command disable-a irukku; receipt end-la feed pannum.

## PC backend start

1. ZIP-ai fresh folder-la extract pannunga. Old database irundhaa backup edunga.
2. CampusPay folder-la PowerShell open pannunga.
3. Run:

```powershell
.\START_DEMO.bat
```

Python 3.12 thevai. Launcher existing demo balances/passwords preserve pannum; migration 0007_android_printing apply pannum. Local login http://127.0.0.1:8002/login.html. Port occupied-na old terminal stop pannunga; illa temporary port select pannunga:

```powershell
$env:CAMPUSPAY_PORT = '8005'
.\START_DEMO.bat
```

Admin ID admin; Merchant ID canteen; initial password CampusDemo@123. Changed password irundhaa adhai use pannunga. Station DEMO-KIOSK-01.

## HTTPS / port-forward testing

Backend PC port 8002 (or selected port) mattum HTTPS tunnel/reverse proxy moolama forward pannunga. Android companion HTTPS origin mattum accept pannum. Example:

```powershell
$env:CAMPUSPAY_WEBAUTHN_ORIGIN = 'https://YOUR-ACTUAL-HOSTNAME'
$env:CAMPUSPAY_WEBAUTHN_RP_ID = 'YOUR-ACTUAL-HOSTNAME'
.\START_DEMO.bat
```

Example placeholders-ai actual hostname-a change pannunga. WebAuthn settings start pannuradhukku munnaadi set pannanum. Same HTTPS hostname web and native app-la use pannunga. Public unauthenticated demo expose pannaama tunnel access control use pannunga; real funds/biometrics test panna vendaam until deployment acceptance. RD ports, printer LAN ports, scanner/printer secrets-ai public-ah forward panna vendaam. Forwarding USB devices-ai PC-ku move pannaadhu; native app kiosk-la dhaan run aaganum.

## Android companion install / printer setup

1. Android 8+ kiosk-ku CampusPay-Android-Hardware-Test.apk copy pannunga. Idhu development-signed TEST APK; production distribution signing/MDM innum separate. APK install permission device-la neengale approve pannunga.
2. Admin > Canteens, menus & stations > Provision / rotate printer key. Matching station-ku key generate pannunga; old key rotate panna queued jobs cancel aagum.
3. CampusPay Hardware app-la HTTPS server origin (slash/path illaama), printer key enter pannunga.
4. USB: select actual printer (Morpho reader-ai select panna vendaam), USB permission grant pannunga. OTG/power hub correct-a irukkanum.
5. Bluetooth: Android settings-la printer pair pannunga; app-la Nearby Devices grant panni paired device select pannunga. BLE-only devices indha SDK Bluetooth port-ku compatible-nu assume panna vendaam.
6. LAN: printer IP and documented port (default 9100; SDK also supports configured port) enter pannunga.
7. Paper setting 58mm/80mm select pannunga. Start printer service press pannunga. Foreground notification-la connection status theriyum. App process restart/stop aana printer key re-enter pannanum; secret persistent storage-la save pannala.
8. Admin Device status check-la printer online confirm pannunga. Notification SDK submission means paper delivery physically confirmed nu artham illa.

## Kiosk activation

Android kiosk browser-la HTTPS /kiosk.html open pannunga. Admin credentials and station ID use pannunga.

- External Morpho kiosk: Authentication = Integrated fingerprint scanner (Android kiosk).
- Phone passkey test: Authentication = Mobile passkey (or Automatic on mobile).
- Companion printer use: Receipt printer = Android thermal printer service.
- Normal Windows/mobile browser printing: Receipt printer = Browser print.

Already activated kiosk-na password-confirmed Logout panni new mode-oda activate pannunga.

Paid order receipt automatic-a display aagum. Print receipt & finish press pannina validated receipt queue-ku pogum. Service submit confirm pannina menu return aagum. Printer offline/UNKNOWN-na receipt retain aagum; another payment panna vendaam. Automatic resend illa; staff existing receipt copy retrieve panni paper situation check pannittu manually print pannalaam. Pending job 90 seconds-ku mela late-a print aagaadhu. Printing timeout 60 seconds; server unknown after 90 seconds. Paper output physically verify pannunga.

## Source build

mobile/android/kiosk-companion folder Android Studio-la open pannunga. JDK 17, Gradle 8.9, Android Gradle Plugin 8.7.3, Android API 35 thevai. Gradle build:

```powershell
.\gradlew.bat assembleDebug
```

Provided test APK Java compiler + official Android aapt2/d8/zipalign/apksigner tools use panni build/signature verify panniyirukku. Gradle/Android Studio build separately execute pannala. Native runtime, manufacturer firmware, permissions, paper status and USB/Bluetooth/LAN real-device test innum execute pannala. Source includes compatibility wrappers for vendor legacy receiver registration on Android 13+.

## Validation result

- Complete backend suite: 204 passed, 10 PostgreSQL-dependent tests skipped.
- Frontend: seven state scenarios passed.
- Android Java compile against actual supplied SDK + API 35 passed.
- Test APK packaging and v2/v3 signature verification passed.
- Browser activation controls verified.
- Physical printer, real Morpho matching, Android runtime, PostgreSQL staging/load, production TLS/backup acceptance pending.

Production-level structure improve panniyirukkom; full hardware production certification claim pannala. Naalaikku web + supported printer acceptance test pannalaam. Morpho student matching-ku vendor MSO SDK still necessary.
