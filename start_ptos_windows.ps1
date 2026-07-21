Write-Host "=========================================="
Write-Host "  PTOS Web Server"
Write-Host "=========================================="
Write-Host ""

Set-Location -Path (Split-Path -Parent $MyInvocation.MyCommand.Path)

if (-not (Test-Path "ptos_web.py")) {
    Write-Host "ERROR: ptos_web.py not found."
    Write-Host "Run this script from the ptos folder."
    Write-Host "Or run setup_ptos_windows.bat to set up first."
    Read-Host "Press Enter to exit"
    exit 1
}

# Find Python 3.11+
function Get-PythonCmd {
    foreach ($cmd in @("py", "python")) {
        if (Get-Command $cmd -ErrorAction SilentlyContinue) {
            $ver = & $cmd -c "import sys; print(sys.version_info>=(3,11))" 2>$null
            if ($ver -eq "True") { return $cmd }
        }
    }
    return $null
}
$python = Get-PythonCmd
if (-not $python) {
    Write-Host "ERROR: Python not found. Run setup_ptos_windows.bat first."
    Read-Host "Press Enter to exit"
    exit 1
}

# Check for updates
if (Test-Path ".git") {
    Write-Host "Checking for updates..."
    $env:GIT_SSL_NO_VERIFY = "1"
    git pull 2>&1 | Out-Null
    $env:GIT_SSL_NO_VERIFY = $null
    if ($LASTEXITCODE -eq 0) { Write-Host "Updated from GitHub." }
    else { Write-Host "Could not reach GitHub - continuing with local version." }
} else {
    Write-Host "Not a git repo - skipping update check."
}

# Dependencies
& $python -c "import flask" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing Flask and tomli-w..."
    & $python -m pip install flask tomli-w pytest --quiet
}

# Kill anything on port 5000
$conn = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    Write-Host "Stopping existing process on port 5000..."
    Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

Write-Host ""
Write-Host "Starting PTOS..."
Write-Host "Open in browser: http://localhost:5000"
Write-Host "Press Ctrl+C to stop."
Write-Host ""

$proc = Start-Process -FilePath $python -ArgumentList "ptos_web.py" -PassThru -NoNewWindow

# Kill Flask when PowerShell exits (even if batch file forces termination)
Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}

# Wait for server to be ready (up to 30s)
Write-Host "Waiting for server..." -NoNewline
$serverReady = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $tcp = [System.Net.Sockets.TcpClient]::new()
        $result = $tcp.ConnectAsync("127.0.0.1", 5000).Wait(1000)
        if ($result) { $serverReady = $true; $tcp.Close(); break }
        $tcp.Close()
    } catch {}
    Write-Host "." -NoNewline
    Start-Sleep -Seconds 1
}
Write-Host ""

if ($serverReady) {
    Start-Process "http://localhost:5000"
} else {
    Write-Host ""
    Write-Host "Server is taking longer than usual to start (startup sync may"
    Write-Host "still be running - check the messages above)."
    Write-Host "Waiting for server to become available..."
    for ($i = 0; $i -lt 120; $i++) {
        try {
            $tcp = [System.Net.Sockets.TcpClient]::new()
            $result = $tcp.ConnectAsync("127.0.0.1", 5000).Wait(1000)
            if ($result) { $tcp.Close(); Start-Process "http://localhost:5000"; break }
            $tcp.Close()
        } catch {}
        Start-Sleep -Seconds 1
    }
}

try {
    Wait-Process -Id $proc.Id -ErrorAction SilentlyContinue
} finally {
    if (-not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}
