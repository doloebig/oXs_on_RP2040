@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
echo ============================================================
echo   oXs Konfig-GUI  -  EXE bauen
echo ============================================================
echo.

REM --- Python suchen: erst PATH (py/python), dann bekannte Orte ---
set "PY="
for %%C in (py python) do (
  if not defined PY ( %%C --version >nul 2>&1 && set "PY=%%C" )
)
if not defined PY (
  for %%P in (
    "%USERPROFILE%\.platformio\penv\Scripts\python.exe"
    "%USERPROFILE%\esptoolenv\Scripts\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "C:\Python313\python.exe"
    "C:\Python312\python.exe"
    "C:\Python311\python.exe"
  ) do (
    if not defined PY if exist "%%~P" ( "%%~P" --version >nul 2>&1 && set "PY=%%~P" )
  )
)

if not defined PY (
  echo Kein Python gefunden.
  echo   -^> Bitte Python 3 aus dem Microsoft Store installieren ^(Suche: "Python 3.12"^)
  echo      und diese Datei danach erneut ausfuehren.
  echo.
  pause & exit /b 1
)
echo Gefundenes Python: !PY!
"!PY!" --version
echo.

REM --- tkinter vorhanden? (fuer die Oberflaeche noetig) ---
"!PY!" -c "import tkinter" 1>nul 2>nul
if errorlevel 1 (
  echo Dieses Python enthaelt KEIN tkinter.
  echo   -^> Bitte Python 3 aus dem Microsoft Store installieren ^(enthaelt tkinter^)
  echo      und diese Datei danach erneut ausfuehren.
  echo.
  pause & exit /b 1
)

REM --- eigene Build-Umgebung (laesst PlatformIO/venv unveraendert) ---
set "VPY=!PY!"
"!PY!" -m venv .buildenv 1>nul 2>nul
if exist ".buildenv\Scripts\python.exe" set "VPY=.buildenv\Scripts\python.exe"
echo Build-Umgebung: !VPY!
echo.

echo [1/2] Installiere pyserial + pyinstaller ...
"!VPY!" -m pip install --upgrade pip pyserial pyinstaller
if errorlevel 1 ( echo Installation fehlgeschlagen. & pause & exit /b 1 )

echo.
echo [2/2] Baue die EXE ...
"!VPY!" -m PyInstaller --onefile --windowed --name oXs_config oXs_config_gui_tk.py
if errorlevel 1 ( echo Build fehlgeschlagen. & pause & exit /b 1 )

echo.
echo ============================================================
echo   Fertig!   Die EXE liegt hier:   dist\oXs_config.exe
echo ============================================================
pause
