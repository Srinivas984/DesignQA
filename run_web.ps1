param([ValidateRange(1024,65535)][int]$Port = 8000)

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    if (!(Test-Path -LiteralPath $python)) {
        python -m venv .venv
        if ($LASTEXITCODE) { throw 'Could not create the Python environment.' }
    }
    & $python -m pip install -r backend/requirements.txt
    if ($LASTEXITCODE) { throw 'Could not install the Python dependencies.' }
    & $python -m playwright install chromium
    if ($LASTEXITCODE) { throw 'Could not install Chromium.' }

    Push-Location frontend
    try {
        npm.cmd ci
        if ($LASTEXITCODE) { throw 'Could not install the frontend dependencies.' }
        npm.cmd run build
        if ($LASTEXITCODE) { throw 'Could not build the frontend.' }
    } finally {
        Pop-Location
    }

    Write-Host "Open http://127.0.0.1:$Port"
    & $python -m uvicorn backend.app:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE) { throw 'DesignQA server could not start.' }
} finally {
    Pop-Location
}
