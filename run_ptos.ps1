# PTOS Launcher for Windows
# Handles both first-time setup and daily launch.
# Usage:  run_ptos.bat (recommended) or  .\run_ptos.ps1

$ErrorActionPreference = "Stop"

function Write-Step($text) {
    Write-Host ""
    Write-Host "--- $text ---"
}

function Write-Banner($text) {
    Write-Host ""
    Write-Host ("=" * 42)
    Write-Host "  $text"
    Write-Host ("=" * 42)
}

# -- 0. Move to script directory --
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# -- 1. Python detection + auto-install --
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
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Python not found. Installing via winget..."
        winget install -e --id Python.Python.3.13 --silent `
            --accept-package-agreements --accept-source-agreements --scope user

        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
        $python = Get-PythonCmd
    }
    if (-not $python) {
        Write-Host ""
        Write-Host "ERROR: Python 3.11+ is required."
        Write-Host "Install it from https://python.org/downloads (tick 'Add to PATH'),"
        Write-Host "or close this window and re-run if you just installed it."
        Read-Host "Press Enter to exit"
        exit 1
    }
}
Write-Host "Using $python"

# -- 2. Git detection + auto-install --
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Git not found. Installing via winget..."
        winget install -e --id Git.Git --silent `
            --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
    }
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host ""
        Write-Host "ERROR: Git is required for PTOS."
        Write-Host "Install from: https://git-scm.com/download/win"
        Write-Host "Or run: winget install Git.Git"
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# -- 2b. Rclone detection + auto-install (best effort) --
if (-not (Get-Command rclone -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "rclone not found. Installing via winget..."
        winget install -e --id Rclone.Rclone --silent `
            --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
    }
    if (-not (Get-Command rclone -ErrorAction SilentlyContinue)) {
        Write-Host "rclone not available - sync feature will be disabled."
        Write-Host "Install later from https://rclone.org/downloads if you want cloud sync."
    }
}

# -- 3. Locate or clone PTOS --
if (Test-Path "$scriptDir\ptos.py") {
    $ptosDir = $scriptDir
} elseif (Test-Path "$scriptDir\ptos\ptos.py") {
    $ptosDir = "$scriptDir\ptos"
} else {
    $ptosDir = "$scriptDir\ptos"
    Write-Step "Cloning PTOS from GitHub"
    $env:GIT_SSL_NO_VERIFY = "1"
    git clone https://github.com/godwinburby/ptos.git $ptosDir
    $env:GIT_SSL_NO_VERIFY = $null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: git clone failed."
        Read-Host "Press Enter to exit"
        exit 1
    }
}
Set-Location $ptosDir
Write-Host "PTOS found at: $ptosDir"

# -- 4. Create data directory (sibling to repo) --
$parentDir = Split-Path -Parent $ptosDir
$dataDir = Join-Path $parentDir "ptos-data"
if (-not (Test-Path $dataDir)) {
    Write-Step "Creating data directory"
    New-Item -ItemType Directory -Path $dataDir | Out-Null
    Write-Host "Data directory created at: $dataDir"
} else {
    Write-Host "Data directory: $dataDir"
}

# -- 5. Write .ptos_home if missing --
if (-not (Test-Path "$ptosDir\.ptos_home")) {
    "$dataDir" | Out-File -Encoding utf8 "$ptosDir\.ptos_home"
    Write-Host "Configured .ptos_home -> $dataDir"
}

# -- 6. Install Flask + tomli-w --
& $python -c "import flask" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Step "Installing Flask and tomli-w"
    & $python -m pip install flask tomli-w --quiet
    if ($LASTEXITCODE -ne 0) {
        & $python -m pip install flask tomli-w
        if ($LASTEXITCODE -ne 0) {
            Write-Host "WARNING: Flask/tomli-w install may have failed."
            Write-Host "You can try manually:  $python -m pip install flask tomli-w"
        } else {
            Write-Host "Flask installed."
        }
    } else {
        Write-Host "Flask ready."
    }
}

# -- 7. First-time init (only if config/ doesn't exist) --
$configDir = Join-Path $dataDir "config"
if (-not (Test-Path $configDir)) {
    Write-Step "Initialising PTOS"
    & $python ptos.py --init
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: ptos --init failed."
        Read-Host "Press Enter to exit"
        exit 1
    }

    Write-Step "Your Name"
    $userName = Read-Host "Enter your name (leave blank for 'User')"
    if ($userName) {
        & $python ptos.py --set-name $userName
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Name set to: $userName"
        } else {
            Write-Host "Warning: Could not set name."
        }
    }
    Write-Host "PTOS initialised."
} else {
    Write-Host "PTOS already initialised (config/ exists)."
}

# -- 8. Git pull (if repo) --
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

# -- 9. Create/update Start_PTOS shortcut in parent directory --
$shortcutPath = Join-Path $parentDir "Start_PTOS.bat"
$batContent = "@echo off`r`npowershell -NoProfile -ExecutionPolicy Bypass -File `"%~dp0ptos\run_ptos.ps1`""
$batContent | Out-File -Encoding ascii $shortcutPath
Write-Host "Shortcut: $shortcutPath"

# -- 10. Kill anything on port 5000 --
Write-Step "Checking port 5000"
$conn = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    foreach ($c in $conn) {
        Write-Host "Stopping process $($c.OwningProcess) on port 5000..."
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 1
}
Write-Host "Port 5000 ready."

# -- 11. Start Flask and open browser --
Write-Banner "Starting PTOS Web Server"
Write-Host "Open in browser: http://localhost:5000"
Write-Host "Press Ctrl+C in this window to stop the server."
Write-Host ""

$proc = Start-Process -FilePath $python -ArgumentList "ptos_web.py" `
    -PassThru -NoNewWindow

# Kill Flask when PowerShell exits
Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action {
    if ($proc -and -not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}

# Health check (up to 15s)
Write-Host "Waiting for server..." -NoNewline
$serverReady = $false
for ($i = 0; $i -lt 15; $i++) {
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

# -- 12. Wait for Flask, then clean up --
try {
    Wait-Process -Id $proc.Id -ErrorAction SilentlyContinue
} finally {
    if (-not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}
