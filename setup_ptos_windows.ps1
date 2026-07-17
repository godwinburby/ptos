# PTOS Setup Script for Windows
# Run via:  setup_ptos_windows.bat   (which launches this script)

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
        Write-Host "or close this window and re-run setup if you just installed it."
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
        Write-Host "ERROR: Git is required for Windows setup."
        Write-Host "Install from: https://git-scm.com/download/win"
        Write-Host "Or run: winget install Git.Git"
        Write-Host "(You may need to close this window and re-run after installing.)"
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# -- 2b. Rclone detection + auto-install --
if (-not (Get-Command rclone -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "rclone not found. Installing via winget..."
        winget install -e --id Rclone.Rclone --silent `
            --accept-package-agreements --accept-source-agreements
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path","User")
    }
    if (-not (Get-Command rclone -ErrorAction SilentlyContinue)) {
        Write-Host ""
        Write-Host "rclone not found. Install from: https://rclone.org/downloads"
        Write-Host "Or run: winget install Rclone.Rclone"
        Read-Host "Press Enter to exit"
        exit 1
    }
}

# -- 3. Locate or clone PTOS --
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (Test-Path "$scriptDir\ptos.py") {
    $ptosDir = $scriptDir
} elseif (Test-Path "$scriptDir\ptos\ptos.py") {
    $ptosDir = "$scriptDir\ptos"
} else {
    $ptosDir = "$scriptDir\ptos"
    Write-Step "Cloning PTOS from GitHub"
    git clone https://github.com/godwinburby/ptos.git $ptosDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: git clone failed."
        Read-Host "Press Enter to exit"
        exit 1
    }
}
Set-Location $ptosDir
Write-Host "PTOS found at: $ptosDir"

# -- 3b. Create data directory (sibling to repo, outside OneDrive) --
$parentDir = Split-Path -Parent $ptosDir
$dataDir = Join-Path $parentDir "ptos-data"
if (-not (Test-Path $dataDir)) {
    Write-Step "Creating data directory"
    New-Item -ItemType Directory -Path $dataDir | Out-Null
    Write-Host "Data directory created at: $dataDir"
} else {
    Write-Host "Data directory exists: $dataDir"
}
"$dataDir" | Out-File -Encoding utf8 (Join-Path $ptosDir ".ptos_home")
Write-Host "Configured .ptos_home -> $dataDir"

# -- 4. Install Flask --
Write-Step "Installing Flask"
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

# -- 5. Initialise PTOS (first run only) --
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

# -- 6. Kill anything on port 5000 --
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

# -- 7. Start Flask and open browser --
Write-Banner "Starting PTOS Web Server"
Write-Host "Open in browser: http://localhost:5000"
Write-Host "Press Ctrl+C in this window to stop the server."
Write-Host ""
Write-Host "To start PTOS next time:  start_ptos_windows.bat"
Write-Host "(Start script automatically updates PTOS if new version available)"
Write-Host ""

$proc = Start-Process -FilePath $python -ArgumentList "ptos_web.py" `
    -PassThru -NoNewWindow

Write-Host "Waiting for server..." -NoNewline
$serverReady = $false
for ($i = 0; $i -lt 15; $i++) {
    try {
        Invoke-WebRequest -Uri "http://localhost:5000" -TimeoutSec 1 -UseBasicParsing | Out-Null
        $serverReady = $true
        break
    } catch {
        if ($_.Exception.Response) { $serverReady = $true; break }
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 1
    }
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
            Invoke-WebRequest -Uri "http://localhost:5000" -TimeoutSec 1 -UseBasicParsing | Out-Null
            Start-Process "http://localhost:5000"
            break
        } catch {
            if ($_.Exception.Response) { Start-Process "http://localhost:5000"; break }
            Start-Sleep -Seconds 1
        }
    }
}

try {
    Wait-Process -Id $proc.Id
} finally {
    if (-not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
}
