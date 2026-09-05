@echo off
REM ============================================================
REM  oXs Konfig-GUI starten (tkinter-Version)
REM  Beim ersten Start wird pyserial automatisch installiert.
REM ============================================================
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo Python wurde nicht gefunden.
  echo Bitte Python 3 installieren - am einfachsten ueber den Microsoft Store:
  echo   Store oeffnen, nach "Python 3.12" suchen, "Installieren".
  echo Danach diese Datei erneut doppelklicken.
  echo.
  pause
  exit /b 1
)

echo Pruefe/installiere pyserial ...
python -m pip install pyserial

echo Starte oXs Konfig-GUI ...
python oXs_config_gui_tk.py
if errorlevel 1 (
  echo.
  echo Die App wurde beendet oder es ist ein Fehler aufgetreten.
  pause
)
