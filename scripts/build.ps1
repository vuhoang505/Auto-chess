$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    throw "The environment is missing. Run .\scripts\setup.ps1 first."
}

& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean ChessVisionAnalyzer.spec

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE. See build\ChessVisionAnalyzer\warn-ChessVisionAnalyzer.txt."
}

$EngineSource = Join-Path $ProjectRoot "engine"
$EngineTarget = Join-Path $ProjectRoot "dist\ChessVisionAnalyzer\engine"
if (Test-Path -LiteralPath $EngineSource) {
    New-Item -ItemType Directory -Force -Path $EngineTarget | Out-Null
    Copy-Item -Path (Join-Path $EngineSource "*") -Destination $EngineTarget -Recurse -Force
    Write-Host "Stockfish: dist\ChessVisionAnalyzer\engine" -ForegroundColor Green
} else {
    Write-Warning "The engine directory is missing; select stockfish.exe in Settings."
}

Write-Host "EXE: dist\ChessVisionAnalyzer\ChessVisionAnalyzer.exe" -ForegroundColor Green
