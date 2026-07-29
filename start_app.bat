@echo off
setlocal
cd /d "%~dp0"

set "PORT=8001"
set "HOST=127.0.0.1"

if not "%~1"=="" set "PORT=%~1"
if not "%~2"=="" set "HOST=%~2"

set "PYTHON_EXE="
if exist "%~dp0.venv\Scripts\python.exe" (
  set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else if exist "%~dp0venv\Scripts\python.exe" (
  set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
) else (
  set "PYTHON_EXE=python"
)

echo Starting Healthcare Management System on %HOST%:%PORT%...
start "Django Server" "%PYTHON_EXE%" backend\manage.py runserver %HOST%:%PORT%
for /L %%I in (1,1,8) do ping 127.0.0.1 -n 2 >nul
set "BROWSER_URL=http://127.0.0.1:%PORT%/"
start "" "%BROWSER_URL%"
echo Server launched. Opened %BROWSER_URL%
endlocal
