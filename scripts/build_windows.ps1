# Build OmniReader Pro for Windows.
#   .\scripts\build_windows.ps1        (uses .venv)
#   .\scripts\build_windows.ps1 -Clean (removes build/ and dist/ first)
param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "No .venv found. Run: python -m venv .venv ; .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

if ($Clean) {
    Write-Host "Cleaning build/ and dist/ ..."
    Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
}

Write-Host "Generating icons..."
& $Py scripts\make_icon.py

Write-Host "Running PyInstaller (this takes a few minutes)..."
& $Py -m PyInstaller packaging\omnireader.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Build complete: dist\OmniReaderPro\OmniReaderPro.exe"
Write-Host "Smoke-test the exe:  .\dist\OmniReaderPro\OmniReaderPro.exe --smoke"