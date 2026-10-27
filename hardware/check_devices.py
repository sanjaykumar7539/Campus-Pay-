"""Read-only kiosk diagnostics. RD READY is not student matching authorization."""
import argparse, json, platform, os
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from xml.etree import ElementTree

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError("RD service redirect rejected")

def describe_rd(data):
    if len(data)>65536 or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("Unsafe or oversized device response")
    root=ElementTree.fromstring(data)
    if root.tag!='RDService':
        raise ValueError("Not an RDService response")
    return {"status":root.attrib.get("status","UNKNOWN"),"info":root.attrib.get("info",""),
        "student_matching_ready":False,
        "note":"RD service discovery does not supply standalone student enrollment/matching."}

def windows_printers():
    if platform.system()!='Windows':return {"status":"NOT_WINDOWS"}
    import winreg
    names=[]
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r"SYSTEM\CurrentControlSet\Control\Print\Printers") as key:
            for i in range(winreg.QueryInfoKey(key)[0]):names.append(winreg.EnumKey(key,i))
    except OSError:
        return {"status":"PRINTER_REGISTRY_UNAVAILABLE","queues":[]}
    return {"status":"QUEUES_FOUND" if names else "NO_QUEUES","queues":names,
        "note":"Installed queues do not establish USB connection, paper availability or successful printing."}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--rd-port',type=int,default=11100)
    args=parser.parse_args()
    if not 1024<=args.rd_port<=65535:parser.error('Invalid port')
    report={"os":platform.system(),"architecture":platform.machine(),"printer":windows_printers()}
    opener=build_opener(NoRedirect(),ProxyHandler({}))
    try:
        request=Request(f'http://127.0.0.1:{args.rd_port}/',method='RDSERVICE')
        with opener.open(request,timeout=2) as response:report['morpho_rd']=describe_rd(response.read(65537))
    except Exception as exc:
        report['morpho_rd']={"status":"NOT_CONFIRMED","error_type":type(exc).__name__,
            "note":"Check vendor service installation and configured port on the physical kiosk."}
    path=os.getenv('CAMPUSPAY_MORPHO_SDK_DIR','')
    report['morpho_sdk']={"configured_directory_exists":bool(path and Path(path).is_dir()),
        "matching_integration_ready":False,"note":"Vendor E2 SDK signatures, license and matcher integration are still required."}
    report['forwarding_note']='Forward the web application only. USB devices stay on the kiosk; run scanner/print services there. Never forward scanner keys or RD service ports.'
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
