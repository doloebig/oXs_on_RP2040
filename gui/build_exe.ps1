# ============================================================
#  oXs Konfig-GUI  -  EXE bauen (PowerShell)
#  Baut dist\oXs_config.exe aus oXs_config_gui_tk.py
# ============================================================
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "============================================================"
Write-Host "  oXs Konfig-GUI  -  EXE bauen"
Write-Host "============================================================"
Write-Host ""

function Test-PyExe($exe) {
    try { & $exe --version *> $null; return ($LASTEXITCODE -eq 0) } catch { return $false }
}

# --- Python suchen: erst PATH (py/python), dann bekannte Orte ---
$PY = $null
foreach ($c in @('py', 'python')) {
    if (Test-PyExe $c) { $PY = $c; break }
}
if (-not $PY) {
    $cands = @(
        "$env:USERPROFILE\.platformio\penv\Scripts\python.exe",
        "$env:USERPROFILE\esptoolenv\Scripts\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "C:\Python313\python.exe", "C:\Python312\python.exe", "C:\Python311\python.exe"
    )
    foreach ($p in $cands) {
        if ((Test-Path $p) -and (Test-PyExe $p)) { $PY = $p; break }
    }
}
if (-not $PY) {
    Write-Host "Kein Python gefunden."
    Write-Host "  -> Bitte Python 3 aus dem Microsoft Store installieren (Suche: 'Python 3.12')"
    Write-Host "     und dieses Skript danach erneut ausfuehren."
    Read-Host "Enter zum Beenden"; exit 1
}
Write-Host "Gefundenes Python: $PY"
& $PY --version
Write-Host ""

# --- tkinter vorhanden? ---
& $PY -c "import tkinter" *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Dieses Python enthaelt KEIN tkinter."
    Write-Host "  -> Bitte Python 3 aus dem Microsoft Store installieren (enthaelt tkinter)"
    Write-Host "     und dieses Skript danach erneut ausfuehren."
    Read-Host "Enter zum Beenden"; exit 1
}

# --- eigene Build-Umgebung (laesst PlatformIO/venv unveraendert) ---
$VPY = $PY
& $PY -m venv .buildenv *> $null
if (Test-Path ".buildenv\Scripts\python.exe") {
    $VPY = (Resolve-Path ".buildenv\Scripts\python.exe").Path
}
Write-Host "Build-Umgebung: $VPY"
Write-Host ""

Write-Host "[1/2] Installiere pyserial + pyinstaller ..."
& $VPY -m pip install --upgrade pip pyserial pyinstaller
if ($LASTEXITCODE -ne 0) { Write-Host "Installation fehlgeschlagen."; Read-Host "Enter zum Beenden"; exit 1 }

Write-Host ""
Write-Host "[2/2] Baue die EXE ..."
& $VPY -m PyInstaller --onefile --windowed --name oXs_config oXs_config_gui_tk.py
if ($LASTEXITCODE -ne 0) { Write-Host "Build fehlgeschlagen."; Read-Host "Enter zum Beenden"; exit 1 }

Write-Host ""
Write-Host "============================================================"
Write-Host "  Fertig!   Die EXE liegt hier:   dist\oXs_config.exe"
Write-Host "============================================================"
Read-Host "Enter zum Beenden"
