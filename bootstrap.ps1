$ErrorActionPreference = "Stop"

function Test-CommandExists {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Resolve-PythonCommand {
    if (Test-CommandExists "py") {
        return @("py", "-3")
    }
    if (Test-CommandExists "python") {
        return @("python")
    }
    if (Test-CommandExists "python3") {
        return @("python3")
    }
    throw "Python 3.10+ was not found. Install Python and retry."
}

Write-Host ""
Write-Host "==> Bootstrapping Alek's Email Assistant"
Write-Host ""

if (-not (Test-CommandExists "node")) {
    throw "Node.js 18+ was not found. Install Node.js and retry."
}
if (-not (Test-CommandExists "npm")) {
    throw "npm was not found. Install Node.js/npm and retry."
}

$pythonCmd = Resolve-PythonCommand
$backendVenvPython = Join-Path $PSScriptRoot "backend\venv\Scripts\python.exe"
$backendPath = Join-Path $PSScriptRoot "backend"
$frontendPath = Join-Path $PSScriptRoot "frontend"

if (-not (Test-Path $backendVenvPython)) {
    Write-Host "==> Creating backend virtual environment..."
    if ($pythonCmd.Length -gt 1) {
        & $pythonCmd[0] $pythonCmd[1] -m venv "backend\venv"
    }
    else {
        & $pythonCmd[0] -m venv "backend\venv"
    }
}

Write-Host "==> Installing backend dependencies..."
& $backendVenvPython -m pip install --upgrade pip
& $backendVenvPython -m pip install -e $backendPath

if (-not (Test-Path (Join-Path $backendPath ".env"))) {
    Write-Host "==> Creating backend/.env from .env.example..."
    Copy-Item (Join-Path $PSScriptRoot ".env.example") (Join-Path $backendPath ".env")
}

Write-Host "==> Installing frontend dependencies..."
Push-Location $frontendPath
try {
    npm install
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host ""
Write-Host "Next steps:"
Write-Host "1) Edit backend/.env and add your API credentials."
Write-Host "2) Start backend:  cd backend; .\venv\Scripts\python.exe -m app.main"
Write-Host "3) Start frontend: cd frontend; npm run dev"
Write-Host "4) Open http://localhost:5173"
Write-Host ""
