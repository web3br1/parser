param(
    [int] $Port = 8000,
    [switch] $SkipCheck,
    [switch] $Reload,
    [switch] $Eager,
    [switch] $FilesystemBroker
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$RunDir = Join-Path $Root ".run"
$LogDir = Join-Path $RunDir "logs"
New-Item -ItemType Directory -Force -Path $RunDir, $LogDir | Out-Null

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

function Test-ProcessRunning {
    param([string] $PidFile)
    if (-not (Test-Path $PidFile)) {
        return $false
    }
    $ExistingPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if (-not $ExistingPid) {
        return $false
    }
    return $null -ne (Get-Process -Id ([int] $ExistingPid) -ErrorAction SilentlyContinue)
}

function Get-RunningPid {
    param([string] $PidFile)
    if (-not (Test-Path $PidFile)) {
        return $null
    }
    $ExistingPid = Get-Content $PidFile -ErrorAction SilentlyContinue
    if (-not $ExistingPid) {
        return $null
    }
    $Process = Get-Process -Id ([int] $ExistingPid) -ErrorAction SilentlyContinue
    if ($Process) {
        return $Process.Id
    }
    return $null
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

    throw "uv not found. Set UV_BIN to the full path of uv.exe."
}

function Set-ProcessEnv {
    param(
        [string] $Name,
        [string] $Value
    )
    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    Set-Item -Path "Env:$Name" -Value $Value
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

function Configure-RuntimeEnv {
    if ($FilesystemBroker) {
        $CeleryDir = Join-Path $RunDir "celery"
        $BrokerDir = Join-Path $CeleryDir "broker"
        $ProcessedDir = Join-Path $CeleryDir "processed"
        New-Item -ItemType Directory -Force -Path $BrokerDir, $ProcessedDir | Out-Null
        Set-ProcessEnv "CELERY_BROKER_URL" "filesystem://"
        Set-ProcessEnv "CELERY_RESULT_BACKEND" "cache+memory://"
        Set-ProcessEnv "CELERY_FILESYSTEM_BROKER_DIR" $BrokerDir
        Set-ProcessEnv "CELERY_FILESYSTEM_PROCESSED_DIR" $ProcessedDir
    }

    if ($Eager) {
        Set-ProcessEnv "CELERY_TASK_ALWAYS_EAGER" "1"
    }
    else {
        Set-ProcessEnv "CELERY_TASK_ALWAYS_EAGER" "0"
    }
    Set-ProcessEnv "API_BASE_URL" "http://localhost:$Port"
}

function Test-ManagedCommandLine {
    param(
        [string] $CommandLine,
        [string[]] $Arguments
    )
    foreach ($Argument in $Arguments) {
        if ([string]::IsNullOrWhiteSpace($Argument)) {
            continue
        }
        if ($CommandLine -notlike "*$Argument*") {
            return $false
        }
    }
    return $true
}

function Stop-StaleManagedProcess {
    param(
        [string] $Name,
        [string[]] $Arguments,
        [Nullable[int]] $ExceptPid = $null
    )

    $CurrentPid = $PID
    Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $CurrentPid `
            -and ($null -eq $ExceptPid -or $_.ProcessId -ne $ExceptPid) `
            -and $_.CommandLine `
            -and (Test-ManagedCommandLine $_.CommandLine $Arguments)
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
        Write-Host ("stopped stale {0} pid={1}" -f $Name, $_.ProcessId)
    }
}

function Start-ManagedProcess {
    param(
        [string] $Name,
        [string[]] $Arguments
    )

    $PidFile = Join-Path $RunDir "$Name.pid"
    $ExistingPid = Get-RunningPid $PidFile
    Stop-StaleManagedProcess $Name $Arguments -ExceptPid $ExistingPid
    if (Test-ProcessRunning $PidFile) {
        Write-Host "$Name already running (pid $(Get-Content $PidFile))"
        return
    }

    $Stdout = Join-Path $LogDir "$Name.out.log"
    $Stderr = Join-Path $LogDir "$Name.err.log"
    $Process = Start-Process `
        -FilePath $UvPath `
        -ArgumentList $Arguments `
        -WorkingDirectory $Root `
        -RedirectStandardOutput $Stdout `
        -RedirectStandardError $Stderr `
        -WindowStyle Hidden `
        -PassThru

    Set-Content -Path $PidFile -Value $Process.Id
    Write-Host ("started {0} pid={1}" -f $Name, $Process.Id)
}

Import-DotEnv (Join-Path $Root ".env")
Normalize-ProcessPathEnv
$UvPath = Resolve-UvPath
Set-ProcessEnv "UV_CACHE_DIR" (Join-Path $Root ".uv-cache")
Configure-RuntimeEnv

if (-not $SkipCheck) {
    & (Join-Path $PSScriptRoot "check_local_stack.ps1")
}
Configure-RuntimeEnv

$ApiArgs = @(
    "run", "--package", "context-builder-api",
    "uvicorn", "context_builder.main:app",
    "--host", "127.0.0.1", "--port", "$Port"
)
if ($Reload) {
    $ApiArgs += "--reload"
}
Start-ManagedProcess "api" $ApiArgs

Start-ManagedProcess "worker-ingest" @(
    "run", "--package", "worker-ingest",
    "celery", "-A", "worker_ingest.celery_app:app",
    "worker", "--loglevel=INFO", "--pool=solo", "-Q", "ingest",
    "--hostname", "parser-worker-ingest@%h"
)

Start-ManagedProcess "worker-classification" @(
    "run", "--package", "worker-classification",
    "celery", "-A", "worker_classification.celery_app:app",
    "worker", "--loglevel=INFO", "--pool=solo", "-Q", "classification",
    "--hostname", "parser-worker-classification@%h"
)

Start-ManagedProcess "worker-extraction" @(
    "run", "--package", "worker-extraction",
    "celery", "-A", "worker_extraction.celery_app:app",
    "worker", "--loglevel=INFO", "--pool=solo", "-Q", "extraction",
    "--hostname", "parser-worker-extraction@%h"
)

Write-Host "Local stack started. Logs: $LogDir"
Write-Host "Health: Invoke-RestMethod http://localhost:8000/health"
