CAMPUSPAY ONE-CLICK BANGALORE LAUNCHER

ON WINDOWS LAPTOP (must have Python 3.12 installed):
1. Extract ZIP.
2. Double click CampusPay\START_CAMPUSPAY.bat.
3. First time needs internet if dependencies are not installed.
4. Leave the black CMD window running.
5. On Windows: http://127.0.0.1:8002/login.html
6. In command window, read the IPv4 address; on Android 11 kiosk connected to the SAME private Wi-Fi, open: http://WINDOWS_IPV4:8002/kiosk.html
   Example: http://192.168.1.10:8002/kiosk.html
7. Firewall prompt: ONLY allow access for Private networks, not Public. If Android cannot access, configure inbound TCP port 8002 in Windows Defender Firewall on Private profile.
8. The kiosk is Android, and .bat does NOT run on Android. It only runs on your Windows host. Android accesses the webpage via the network.

IMPORTANT LIMITATIONS:
* Real fingerprint capture/matching still needs the actual scanner SDK and Android adapter.
* Real thermal printing still needs the approved printer SDK, vendor compatibility and a tested Android companion APK.
* HTTP over the private LAN is for TESTING ONLY, not real money/production or real student data. Use HTTPS and protected credentials for a real deployment.
* Demo logins/data follow DEMO_LOGINS.md. The demo database lives in backend\campuspay_common_demo.db and is retained on repeat runs.
* The batch runner does not install an APK, hardware driver, or Android SDK on the kiosk.

STOP SERVER: close the CMD window or press Ctrl+C there.
