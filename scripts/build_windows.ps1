# Build Veyrion Workspace for Windows.
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

Write-Host "Generating sample documents..."
$env:PYTHONPATH = Join-Path $Root "src"
& $Py scripts\make_sample_documents.py
Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue

Write-Host "Running PyInstaller (this takes a few minutes)..."
& $Py -m PyInstaller packaging\veyrion.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Build complete: dist\VeyrionWorkspace\VeyrionWorkspace.exe"
Write-Host "Smoke-test the exe:  `$env:VEYRION_SMOKE=2; .\dist\VeyrionWorkspace\VeyrionWorkspace.exe"