@echo off
:: Registers Veloce Native Messaging Host in Windows Registry for Chrome and Edge
setlocal

set "SCRIPT_DIR=%~dp0"
set "MANIFEST_PATH=%SCRIPT_DIR%com.veloce.native_host.json"

:: Write manifest with absolute path for Windows
echo {> "%MANIFEST_PATH%"
echo   "name": "com.veloce.native_host",>> "%MANIFEST_PATH%"
echo   "description": "Veloce Native Messaging Host",>> "%MANIFEST_PATH%"
echo   "path": "%SCRIPT_DIR%native_host.bat",>> "%MANIFEST_PATH%"
echo   "type": "stdio",>> "%MANIFEST_PATH%"
echo   "allowed_origins": [>> "%MANIFEST_PATH%"
echo     "chrome-extension://*/">> "%MANIFEST_PATH%"
echo   ]>> "%MANIFEST_PATH%"
echo }>> "%MANIFEST_PATH%"

:: Create wrapper runner for Python on Windows
echo @echo off > "%SCRIPT_DIR%native_host.bat"
echo python "%SCRIPT_DIR%native_host.py" >> "%SCRIPT_DIR%native_host.bat"

:: Register for Google Chrome
reg add "HKCU\Software\Google\Chrome\NativeMessagingHosts\com.veloce.native_host" /ve /t REG_SZ /d "%MANIFEST_PATH%" /f >nul 2>&1
:: Register for Microsoft Edge
reg add "HKCU\Software\Microsoft\Edge\NativeMessagingHosts\com.veloce.native_host" /ve /t REG_SZ /d "%MANIFEST_PATH%" /f >nul 2>&1

echo [OK] Veloce Native Messaging Host registered for Chrome and Edge on Windows!
pause

