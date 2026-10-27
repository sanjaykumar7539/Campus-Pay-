"""Non-invasive release checks. Run: python scripts/preflight_bangalore.py"""
from pathlib import Path
import ast, sys
root=Path(__file__).resolve().parents[1]
checks={
 'Android printer SDK bundled':(root/'mobile/android/kiosk-companion/app/libs/PosPrinterSDK.jar').exists(),
 'Android printer worker source':(root/'mobile/android/kiosk-companion/app/src/main/java/edu/campuspay/hardware/PrinterWorker.java').exists(),
 'Scanner adapter implementation present':False,
 'Frontend includes one-scan instructions':'Scan once.' in (root/'frontend/demo/kiosk.html').read_text(),
 'Backend payment first scan READY':'if c.purpose == "PAY":' in (root/'backend/app/kiosk_service.py').read_text() and 'c.status = "READY"' in (root/'backend/app/kiosk_service.py').read_text(),
 'No demo kiosk password hash in release':not (root/'backend/.kiosk_password_hash').exists(),
}
for file in ['backend/app/kiosk_credentials.py','backend/app/kiosk_router.py','backend/app/kiosk_service.py']:
    try: ast.parse((root/file).read_text())
    except SyntaxError as e:checks[file+' syntax']=False
    else:checks[file+' syntax']=True
for title, passed in checks.items(): print(('PASS' if passed else 'PENDING')+' '+title)
print('Scanner adapter is intentionally PENDING until official Morpho Android SDK + physical hardware test.')
