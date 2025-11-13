# Start backend services with visible output
# This version shows all output in the console

# Get script directory and change to project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Check if virtual environment exists, create if not
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& "venv\Scripts\Activate.ps1"

# Check if dependencies are installed
Write-Host "Checking dependencies..." -ForegroundColor Yellow
$pythonExe = Join-Path $ScriptDir "venv\Scripts\python.exe"
try {
    & $pythonExe -c "import websockets" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "websockets not installed"
    }
} catch {
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    & $pythonExe -m pip install -r requirements.txt
}

# Kill any existing processes on these ports
Write-Host "Cleaning up existing processes..." -ForegroundColor Yellow
$port8000 = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
$port8765 = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique

if ($port8000) {
    Stop-Process -Id $port8000 -Force -ErrorAction SilentlyContinue
}
if ($port8765) {
    Stop-Process -Id $port8765 -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 2
Write-Host "Ports cleared" -ForegroundColor Green

Write-Host ""
Write-Host "Starting backend services..." -ForegroundColor Yellow
Write-Host "FastAPI: http://localhost:8000" -ForegroundColor Cyan
Write-Host "WebSocket: ws://localhost:8765" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop both services" -ForegroundColor Yellow
Write-Host ""

# Start both services - WebSocket in foreground, API in background but with output
$apiJob = Start-Job -ScriptBlock {
    Set-Location $using:ScriptDir
    $pythonExe = Join-Path $using:ScriptDir "venv\Scripts\python.exe"
    & $pythonExe -m uvicorn backend.api:app --reload --port 8000 2>&1
}

# Start WebSocket server in foreground (this will show output)
try {
    & $pythonExe -m backend.websocket_server
} finally {
    Write-Host "`nStopping services..." -ForegroundColor Yellow
    Stop-Job -Job $apiJob -ErrorAction SilentlyContinue
    Remove-Job -Job $apiJob -ErrorAction SilentlyContinue
    Write-Host "Services stopped." -ForegroundColor Green
}

