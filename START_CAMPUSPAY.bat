@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title CampusPay - Bangalore One Click Demo
color 0A
echo =====================================================
echo                 CAMPUSPAY DEMO STARTER
echo =====================================================
echo.
echo Machine: Windows PC / laptop only, NOT Android kiosk.
echo For local demo: http://127.0.0.1:8002/login.html
echo.
set "CAMPUSPAY_PORT=8002"
rem LAN mode exposes demo login over unencrypted HTTP; only use private isolated Wi-Fi.
rem Change to 127.0.0.1 for Windows-only access.
set "CAMPUSPAY_HOST=0.0.0.0"
set "PYTHON_EXE="
if exist "backend\.venv\Scripts\python.exe" set "PYTHON_EXE=backend\.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"
if not defined PYTHON_EXE (
  echo [SETUP] Creating Python 3.12 environment...
  py -3.12 -m venv backend\.venv
  if errorlevel 1 goto no_python
  set "PYTHON_EXE=backend\.venv\Scripts\python.exe"
)
"%PYTHON_EXE%" -c "import sys; assert sys.version_info[:2] == (3,12), 'Python 3.12 required'"
if errorlevel 1 goto failed
"%PYTHON_EXE%" -c "import fastapi, sqlalchemy, bcrypt, uvicorn, alembic, jwt, webauthn"
if errorlevel 1 (
  echo [SETUP] Installing required packages. Internet needed only on first setup.
  "%PYTHON_EXE%" -m pip install --disable-pip-version-check -r backend\requirements.txt
  if errorlevel 1 goto failed
)
echo.
echo [INFO] Current network addresses (look for IPv4 Address):
ipconfig | findstr /i "IPv4"
echo.
echo [INFO] Android kiosk must use your Windows IPv4 address, same Wi-Fi/LAN.
echo [INFO] Example: http://192.168.1.10:8002/kiosk.html
echo [INFO] Windows Firewall may need inbound TCP 8002 allowed on PRIVATE network.
echo [INFO] Scanner + thermal printer still REQUIRE Android vendor SDK/companion.
echo [INFO] Leave this CMD window OPEN while testing.
echo.
rem Open local page after a small delay; server starts below.
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 5; Start-Process http://127.0.0.1:8002/login.html"
echo [START] Starting backend...
"%PYTHON_EXE%" start_demo.py
if errorlevel 1 goto failed
goto end
:no_python
echo [ERROR] Python 3.12 unavailable. Install it from python.org.
goto failed
:failed
echo.
echo [ERROR] CampusPay failed to start. Read the error above.
pause
exit /b 1
:end
echo [INFO] CampusPay stopped. Press any key to close.
pause >nul
exit /b 0
