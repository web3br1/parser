param(
    [int] $Port = 6379,
    [switch] $ForceDownload
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$RunDir = Join-Path $Root ".run"
# Portable Redis lives under .run\redis so it stays local to this workspace.
$RedisDir = Join-Path $RunDir "redis"
$LogDir = Join-Path $RunDir "logs"
$PidFile = Join-Path $RunDir "redis.pid"
$ZipPath = Join-Path $RedisDir "redis-windows.zip"
$InstallDir = Join-Path $RedisDir "portable"
$RedisServer = Join-Path $InstallDir "redis-server.exe"
$RedisConfig = Join-Path $InstallDir "redis.local.conf"
$RedisLog = Join-Path $LogDir "redis.out.log"
$RedisErr = Join-Path $LogDir "redis.err.log"

$env:REDIS_VERSION = if ($env:REDIS_VERSION) { $env:REDIS_VERSION } else { "5.0.14.1" }
$DownloadUrl = "https://github.com/tporadowski/redis/releases/download/v$env:REDIS_VERSION/Redis-x64-$env:REDIS_VERSION.zip"

New-Item -ItemType Directory -Force -Path $RedisDir, $LogDir | Out-Null

function Test-RedisTcp {
    param([int] $TargetPort)
    $Client = [System.Net.Sockets.TcpClient]::new()
    try {
        $Task = $Client.ConnectAsync("127.0.0.1", $TargetPort)
        if (-not $Task.Wait(1000)) {
            return $false
        }
        return $Client.Connected
    }
    finally {
        $Client.Dispose()
    }
}

function Test-ProcessRunning {
    param([string] $TargetPidFile)
    if (-not (Test-Path $TargetPidFile)) {
        return $false
    }
    $ExistingPid = Get-Content $TargetPidFile -ErrorAction SilentlyContinue
    if (-not $ExistingPid) {
        return $false
    }
    return $null -ne (Get-Process -Id ([int] $ExistingPid) -ErrorAction SilentlyContinue)
}

function Normalize-ProcessPathEnv {
    $PathValue = [Environment]::GetEnvironmentVariable("Path", "Process")
    if (-not $PathValue) {
        $PathValue = [Environment]::GetEnvironmentVariable("PATH", "Process")
    }
    if ($PathValue) {
        [Environment]::SetEnvironmentVariable("PATH", $null, "Process")
        [Environment]::SetEnvironmentVariable("Path", $PathValue, "Process")
    }
}

if (Test-RedisTcp $Port) {
    Write-Host "Redis already reachable on localhost:$Port"
    Write-Host "REDIS_URL=redis://localhost:$Port/0"
    exit 0
}

if (-not (Test-Path $RedisServer) -or $ForceDownload) {
    if ($ForceDownload -and (Test-Path $InstallDir)) {
        Remove-Item -LiteralPath $InstallDir -Recurse -Force
    }
    if (-not (Test-Path $ZipPath) -or $ForceDownload) {
        Write-Host "Downloading portable Redis from tporadowski/redis v$env:REDIS_VERSION..."
        Invoke-WebRequest -Uri $DownloadUrl -OutFile $ZipPath
    }
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    Expand-Archive -Path $ZipPath -DestinationPath $InstallDir -Force
}

if (Test-ProcessRunning $PidFile) {
    Write-Host "Redis process already running (pid $(Get-Content $PidFile))"
    Write-Host "REDIS_URL=redis://localhost:$Port/0"
    exit 0
}

@"
port $Port
bind 127.0.0.1
save ""
appendonly no
"@ | Set-Content -Path $RedisConfig -Encoding ASCII

Normalize-ProcessPathEnv
$Process = Start-Process `
    -FilePath $RedisServer `
    -ArgumentList @("redis.local.conf") `
    -WorkingDirectory $InstallDir `
    -RedirectStandardOutput $RedisLog `
    -RedirectStandardError $RedisErr `
    -WindowStyle Hidden `
    -PassThru

Set-Content -Path $PidFile -Value $Process.Id
Start-Sleep -Seconds 2

if (-not (Test-RedisTcp $Port)) {
    throw "Redis did not become reachable on localhost:$Port. Check $RedisErr"
}

Write-Host "Redis portable started pid=$($Process.Id)"
Write-Host "REDIS_URL=redis://localhost:$Port/0"
Write-Host "Logs: $RedisLog"
