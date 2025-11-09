# Start backend services for Windows
# PowerShell script to start FastAPI and WebSocket servers

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

# Kill any existing processes on these ports (Windows version)
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

# Start FastAPI server in background job
Write-Host "Starting FastAPI server..." -ForegroundColor Yellow
$apiJob = Start-Job -ScriptBlock {
    Set-Location $using:ScriptDir
    $pythonExe = Join-Path $using:ScriptDir "venv\Scripts\python.exe"
    & $pythonExe -m uvicorn backend.api:app --reload --port 8000
}

# Start WebSocket server in background job
Write-Host "Starting WebSocket server..." -ForegroundColor Yellow
$wsJob = Start-Job -ScriptBlock {
    Set-Location $using:ScriptDir
    $pythonExe = Join-Path $using:ScriptDir "venv\Scripts\python.exe"
    & $pythonExe -m backend.websocket_server
}

Write-Host ""
Write-Host "Backend services started!" -ForegroundColor Green
Write-Host "FastAPI: http://localhost:8000" -ForegroundColor Cyan
Write-Host "WebSocket: ws://localhost:8765" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

# Keep script running and monitor jobs
try {
    while ($true) {
        # Check if jobs are still running
        if ($apiJob.State -eq "Failed" -or $wsJob.State -eq "Failed") {
            Write-Host "One or more services failed. Check job output:" -ForegroundColor Red
            Receive-Job -Job $apiJob, $wsJob
            break
        }
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Host "`nStopping services..." -ForegroundColor Yellow
    Stop-Job -Job $apiJob, $wsJob -ErrorAction SilentlyContinue
    Remove-Job -Job $apiJob, $wsJob -ErrorAction SilentlyContinue
    Write-Host "Services stopped." -ForegroundColor Green
}

