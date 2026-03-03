param(
    [switch]$SetupOnly
)

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

function Resolve-NpmCommand {
    if (Test-CommandExists "npm.cmd") {
        return "npm.cmd"
    }
    if (Test-CommandExists "npm") {
        return "npm"
    }
    throw "npm was not found. Install Node.js/npm and retry."
}

function Get-EnvValue {
    param(
        [string]$Path,
        [string]$Key
    )
    if (-not (Test-Path $Path)) {
        return ""
    }
    $line = Get-Content $Path | Where-Object { $_ -match "^$([regex]::Escape($Key))=" } | Select-Object -First 1
    if (-not $line) {
        return ""
    }
    return ($line -replace "^$([regex]::Escape($Key))=", "")
}

function Set-EnvValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )
    $lines = @()
    if (Test-Path $Path) {
        $lines = [System.Collections.Generic.List[string]](Get-Content $Path)
    }
    else {
        $lines = [System.Collections.Generic.List[string]]::new()
    }

    $pattern = "^$([regex]::Escape($Key))="
    $updated = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $pattern) {
            $lines[$i] = "$Key=$Value"
            $updated = $true
            break
        }
    }

    if (-not $updated) {
        $lines.Add("$Key=$Value")
    }

    Set-Content -Path $Path -Value $lines
}

function Read-SecretPrompt {
    param([string]$Prompt)
    $secure = Read-Host -Prompt $Prompt -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

function Ensure-RequiredEnv {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Prompt
    )
    $existing = Get-EnvValue -Path $Path -Key $Key
    if ($existing) {
        return
    }

    while ($true) {
        $value = Read-SecretPrompt -Prompt $Prompt
        if ($value) {
            Set-EnvValue -Path $Path -Key $Key -Value $value
            break
        }
        Write-Host "$Key is required."
    }
}

function Ensure-OptionalEnv {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Prompt
    )
    $existing = Get-EnvValue -Path $Path -Key $Key
    if ($existing) {
        return
    }
    $value = Read-Host -Prompt "$Prompt (optional, press Enter to skip)"
    if ($value) {
        Set-EnvValue -Path $Path -Key $Key -Value $value
    }
}

function Ensure-AnthropicModel {
    param([string]$Path)
    $defaultModel = "claude-sonnet-4-20250514"
    $current = (Get-EnvValue -Path $Path -Key "ANTHROPIC_MODEL").Trim()

    if (-not $current) {
        Set-EnvValue -Path $Path -Key "ANTHROPIC_MODEL" -Value $defaultModel
        Write-Host "Set ANTHROPIC_MODEL=$defaultModel"
        return
    }

    # Guard against accidental API key paste into model field.
    if ($current -match '^sk-ant-') {
        Write-Host "ANTHROPIC_MODEL looked like an API key; resetting to $defaultModel"
        Set-EnvValue -Path $Path -Key "ANTHROPIC_MODEL" -Value $defaultModel
    }
}

function Test-PortListening {
    param([int]$Port)
    try {
        $connections = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop
        return ($connections | Measure-Object).Count -gt 0
    }
    catch {
        return $false
    }
}

function Wait-UrlReady {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 90
    )
    $start = Get-Date
    while (((Get-Date) - $start).TotalSeconds -lt $TimeoutSeconds) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        }
        catch {
            Start-Sleep -Milliseconds 800
        }
    }
    return $false
}

Write-Host ""
Write-Host "==> Bootstrapping Alek's Email Assistant"
Write-Host ""

if (-not (Test-CommandExists "node")) {
    throw "Node.js 18+ was not found. Install Node.js and retry."
}

$npmCmd = Resolve-NpmCommand
$pythonCmd = Resolve-PythonCommand
$backendPath = Join-Path $PSScriptRoot "backend"
$frontendPath = Join-Path $PSScriptRoot "frontend"
$runPath = Join-Path $PSScriptRoot ".run"
$backendVenvPython = Join-Path $backendPath "venv\Scripts\python.exe"
$backendEnvPath = Join-Path $backendPath ".env"
$backendOutLog = Join-Path $runPath "backend.out.log"
$backendErrLog = Join-Path $runPath "backend.err.log"
$backendPidPath = Join-Path $runPath "backend.pid"
$frontendOutLog = Join-Path $runPath "frontend.out.log"
$frontendErrLog = Join-Path $runPath "frontend.err.log"
$frontendPidPath = Join-Path $runPath "frontend.pid"

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

if (-not (Test-Path $backendEnvPath)) {
    Write-Host "==> Creating backend/.env from .env.example..."
    Copy-Item (Join-Path $PSScriptRoot ".env.example") $backendEnvPath
}

Write-Host "==> Capturing API credentials..."
Ensure-RequiredEnv -Path $backendEnvPath -Key "ANTHROPIC_API_KEY" -Prompt "Enter ANTHROPIC_API_KEY"
Ensure-AnthropicModel -Path $backendEnvPath
Ensure-RequiredEnv -Path $backendEnvPath -Key "NYLAS_API_KEY" -Prompt "Enter NYLAS_API_KEY"
Ensure-RequiredEnv -Path $backendEnvPath -Key "NYLAS_CLIENT_ID" -Prompt "Enter NYLAS_CLIENT_ID"
Ensure-RequiredEnv -Path $backendEnvPath -Key "NYLAS_CLIENT_SECRET" -Prompt "Enter NYLAS_CLIENT_SECRET"

$grantId = Get-EnvValue -Path $backendEnvPath -Key "NYLAS_GRANT_ID"
$sid = Get-EnvValue -Path $backendEnvPath -Key "NYLAS_SID"
if (-not $grantId -and -not $sid) {
    Ensure-RequiredEnv -Path $backendEnvPath -Key "NYLAS_GRANT_ID" -Prompt "Enter NYLAS_GRANT_ID (preferred) or use NYLAS_SID in .env"
}

Ensure-RequiredEnv -Path $backendEnvPath -Key "DEEPGRAM_API_KEY" -Prompt "Enter DEEPGRAM_API_KEY"
Ensure-RequiredEnv -Path $backendEnvPath -Key "CARTESIA_API_KEY" -Prompt "Enter CARTESIA_API_KEY"

Write-Host "==> Installing frontend dependencies..."
Push-Location $frontendPath
try {
    & $npmCmd install
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host ""

if ($SetupOnly) {
    Write-Host "Setup-only mode enabled. Skipping service startup."
    exit 0
}

if (-not (Test-Path $runPath)) {
    New-Item -ItemType Directory -Path $runPath | Out-Null
}

if (-not (Test-PortListening -Port 8000)) {
    Write-Host "==> Starting backend server on http://localhost:8000 ..."
    $backendProc = Start-Process `
        -FilePath $backendVenvPython `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000") `
        -WorkingDirectory $backendPath `
        -RedirectStandardOutput $backendOutLog `
        -RedirectStandardError $backendErrLog `
        -PassThru
    Set-Content -Path $backendPidPath -Value $backendProc.Id
}
else {
    Write-Host "==> Backend already listening on port 8000."
}

if (-not (Test-PortListening -Port 5173)) {
    Write-Host "==> Starting frontend dashboard on http://localhost:5173 ..."
    $frontendProc = Start-Process `
        -FilePath "npm.cmd" `
        -ArgumentList @("run", "dev", "--", "--host", "0.0.0.0", "--port", "5173") `
        -WorkingDirectory $frontendPath `
        -RedirectStandardOutput $frontendOutLog `
        -RedirectStandardError $frontendErrLog `
        -PassThru
    Set-Content -Path $frontendPidPath -Value $frontendProc.Id
}
else {
    Write-Host "==> Frontend already listening on port 5173."
}

Write-Host "==> Waiting for backend health..."
$backendReady = Wait-UrlReady -Url "http://localhost:8000/health" -TimeoutSeconds 120
Write-Host "==> Waiting for frontend..."
$frontendReady = Wait-UrlReady -Url "http://localhost:5173/" -TimeoutSeconds 120

if ($backendReady -and $frontendReady) {
    Write-Host "==> Services are ready. Opening browser..."
    Start-Process "http://localhost:5173/"
}
else {
    Write-Host "One or more services did not become ready in time."
    Write-Host "Backend logs:  $backendErrLog"
    Write-Host "Frontend logs: $frontendErrLog"
}

Write-Host ""
Write-Host "Run status:"
Write-Host "Backend health:  $(if ($backendReady) { "ready" } else { "not ready" })"
Write-Host "Frontend status: $(if ($frontendReady) { "ready" } else { "not ready" })"
Write-Host "Backend PID file:  $backendPidPath"
Write-Host "Frontend PID file: $frontendPidPath"
Write-Host ""
Write-Host "To stop services:"
Write-Host "  Stop-Process -Id (Get-Content `"$backendPidPath`", `"$frontendPidPath`")"
