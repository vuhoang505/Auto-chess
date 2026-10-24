param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$PythonCommand = $null
try {
    $null = & py -3.12 --version 2>&1
    if ($LASTEXITCODE -eq 0) { $PythonCommand = @("py", "-3.12") }
} catch {}

if (-not $PythonCommand) {
    $candidate = Get-Command python -ErrorAction SilentlyContinue
    if ($candidate) {
        $version = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($version -eq "3.12") { $PythonCommand = @("python") }
    }
}

if (-not $PythonCommand) {
    throw "Python 3.12 was not found. Install it from https://www.python.org/downloads/windows/ and run this script again."
}

if (Test-Path -LiteralPath ".venv\Scripts\python.exe") {
    $venvVersion = & .\.venv\Scripts\python.exe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ($venvVersion -ne "3.12") {
        throw ".venv uses Python $venvVersion. Rename that directory and run this script again to create a Python 3.12 environment."
    }
} else {
    if ($PythonCommand.Count -eq 2) {
        & $PythonCommand[0] $PythonCommand[1] -m venv .venv
    } else {
        & $PythonCommand[0] -m venv .venv
    }
}

if (-not $SkipInstall) {
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip." }

    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Could not install the runtime dependencies." }

    # Defender can block the unused runw.exe bootloader on some computers. This
    # app uses run.exe and hides its own console, so the fallback safely omits it.
    & .\.venv\Scripts\python.exe -m pip install "PyInstaller>=6.11,<7"
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Normal PyInstaller installation was blocked; using the Defender-compatible fallback."
        & .\.venv\Scripts\python.exe -m pip install altgraph pefile pyinstaller-hooks-contrib pywin32-ctypes setuptools
        if ($LASTEXITCODE -ne 0) { throw "Could not install the PyInstaller dependencies." }

        $PyInstallerCache = Join-Path $ProjectRoot ".build-cache\pyinstaller"
        New-Item -ItemType Directory -Force -Path $PyInstallerCache | Out-Null
        & .\.venv\Scripts\python.exe -m pip download --no-deps --only-binary=:all: --dest $PyInstallerCache "PyInstaller>=6.11,<7"
        if ($LASTEXITCODE -ne 0) { throw "Could not download the PyInstaller wheel." }

        $PyInstallerWheel = Get-ChildItem -LiteralPath $PyInstallerCache -Filter "pyinstaller-*.whl" |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if (-not $PyInstallerWheel) { throw "The downloaded PyInstaller wheel was not found." }

        # A relative path avoids a bsdtar Unicode path bug on older Windows.
        $RelativeWheel = Resolve-Path -Relative $PyInstallerWheel.FullName
        tar.exe `
            --exclude="PyInstaller/bootloader/Windows-64bit-intel/runw.exe" `
            --exclude="PyInstaller/bootloader/Windows-64bit-intel/runw_d.exe" `
            -xf $RelativeWheel `
            -C ".venv\Lib\site-packages"
        if ($LASTEXITCODE -ne 0) { throw "Could not extract the Defender-compatible PyInstaller package." }
    }

    & .\.venv\Scripts\python.exe -m PyInstaller --version
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller is not ready." }
}

Write-Host "Ready. Run: .\.venv\Scripts\python.exe main.py" -ForegroundColor Green
