Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

function Write-Check {
    param(
        [string] $Name,
        [bool] $Ok,
        [string] $Detail = ""
    )
    $Status = if ($Ok) { "OK" } else { "FAIL" }
    $Line = "[{0}] {1}" -f $Status, $Name
    if ($Detail) {
        $Line = "{0} - {1}" -f $Line, $Detail
    }
    Write-Host $Line
}

function Import-DotEnv {
    param([string] $Path)
    if (-not (Test-Path $Path)) {
        throw ".env not found at $Path"
    }

    Get-Content $Path | ForEach-Object {
        $Line = $_.Trim()
        if (-not $Line -or $Line.StartsWith("#") -or -not $Line.Contains("=")) {
            return
        }
        $Parts = $Line.Split("=", 2)
        $Name = $Parts[0].Trim()
        $Value = $Parts[1].Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
}

function Resolve-UvPath {
    $EnvUv = [Environment]::GetEnvironmentVariable("UV_BIN", "Process")
    if ($EnvUv -and (Test-Path $EnvUv)) {
        return (Resolve-Path $EnvUv).Path
    }

    $Command = Get-Command "uv" -ErrorAction SilentlyContinue
    if ($Command) {
        return $Command.Source
    }

    $Candidates = @(
        (Join-Path $env:USERPROFILE "miniforge3\Scripts\uv.exe"),
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe")
    )
    foreach ($Candidate in $Candidates) {
        if (Test-Path $Candidate) {
            return (Resolve-Path $Candidate).Path
        }
    }

    return $null
}

function Test-TcpEndpoint {
    param(
        [string] $HostName,
        [int] $Port
    )

    $Client = [System.Net.Sockets.TcpClient]::new()
    try {
        $Task = $Client.ConnectAsync($HostName, $Port)
        if (-not $Task.Wait(1500)) {
            return $false
        }
        return $Client.Connected
    }
    finally {
        $Client.Dispose()
    }
}

function Test-ManagedCommandLine {
    param(
        [string] $CommandLine,
        [string[]] $Needles
    )
    foreach ($Needle in $Needles) {
        if ($CommandLine -notlike "*$Needle*") {
            return $false
        }
    }
    return $true
}

function Count-ManagedProcesses {
    param([string[]] $Needles)

    $CurrentPid = $PID
    $Matches = @(
        Get-CimInstance Win32_Process | Where-Object {
            $_.ProcessId -ne $CurrentPid `
                -and $_.CommandLine `
                -and (Test-ManagedCommandLine $_.CommandLine $Needles)
        }
    )
    return $Matches.Count
}

$Failures = 0

$UvPath = Resolve-UvPath
Write-Check "uv" ($null -ne $UvPath) $UvPath
if (-not $UvPath) { $Failures += 1 }

$NpxFound = $null -ne (Get-Command "npx" -ErrorAction SilentlyContinue)
Write-Check "npx" $NpxFound
if (-not $NpxFound) { $Failures += 1 }

try {
    Import-DotEnv (Join-Path $Root ".env")
    Write-Check ".env" $true
}
catch {
    Write-Check ".env" $false $_.Exception.Message
    exit 1
}

$RequiredEnv = @(
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "WORKSPACE_STORAGE_BUCKET",
    "API_BASE_URL"
)

foreach ($Name in $RequiredEnv) {
    $Value = [Environment]::GetEnvironmentVariable($Name, "Process")
    $Ok = -not [string]::IsNullOrWhiteSpace($Value)
    Write-Check $Name $Ok
    if (-not $Ok) { $Failures += 1 }
}

$BrokerUrl = [Environment]::GetEnvironmentVariable("CELERY_BROKER_URL", "Process")
$RedisUrl = [Environment]::GetEnvironmentVariable("REDIS_URL", "Process")
if ($BrokerUrl -and $BrokerUrl.StartsWith("filesystem://")) {
    $BrokerDir = [Environment]::GetEnvironmentVariable("CELERY_FILESYSTEM_BROKER_DIR", "Process")
    $BrokerOk = -not [string]::IsNullOrWhiteSpace($BrokerDir)
    Write-Check "celery filesystem broker" $BrokerOk $BrokerDir
    if (-not $BrokerOk) { $Failures += 1 }
}
elseif ($RedisUrl) {
    try {
        $Uri = [Uri] $RedisUrl
        $Port = if ($Uri.Port -gt 0) { $Uri.Port } else { 6379 }
        $Ok = Test-TcpEndpoint $Uri.Host $Port
        Write-Check "redis tcp" $Ok ("{0}:{1}" -f $Uri.Host, $Port)
        if (-not $Ok) { $Failures += 1 }
    }
    catch {
        Write-Check "REDIS_URL parse" $false $_.Exception.Message
        $Failures += 1
    }
}
else {
    Write-Check "REDIS_URL or CELERY_BROKER_URL" $false
    $Failures += 1
}

$WorkerSpecs = @(
    @{ Name = "worker-ingest"; Needles = @("celery", "worker_ingest.celery_app:app") },
    @{ Name = "worker-classification"; Needles = @("celery", "worker_classification.celery_app:app") },
    @{ Name = "worker-extraction"; Needles = @("celery", "worker_extraction.celery_app:app") }
)
foreach ($Spec in $WorkerSpecs) {
    $Count = Count-ManagedProcesses $Spec.Needles
    $Ok = $Count -le 1
    Write-Check "duplicate $($Spec.Name)" $Ok ("count={0}" -f $Count)
    if (-not $Ok) {
        Write-Host "Duplicate worker processes detected. Run .\scripts\dev\stop_local_stack.ps1 before starting the stack."
        $Failures += 1
    }
}

if ($Failures -gt 0) {
    throw "$Failures local stack preflight check(s) failed"
}

Write-Host "Local stack preflight passed."
