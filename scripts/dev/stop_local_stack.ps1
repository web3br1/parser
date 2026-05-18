Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$RunDir = Join-Path $Root ".run"

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

function Stop-ManagedProcessByCommand {
    param(
        [string] $Name,
        [string[]] $Needles
    )

    $CurrentPid = $PID
    Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $CurrentPid `
            -and $_.CommandLine `
            -and (Test-ManagedCommandLine $_.CommandLine $Needles)
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force
        Write-Host ("stopped {0} pid={1}" -f $Name, $_.ProcessId)
    }
}

if (-not (Test-Path $RunDir)) {
    Write-Host "No .run directory found; checking for pidless managed processes."
}

if (Test-Path $RunDir) {
    Get-ChildItem $RunDir -Filter "*.pid" | ForEach-Object {
        $Name = $_.BaseName
        $PidValue = Get-Content $_.FullName -ErrorAction SilentlyContinue
        if ($PidValue) {
            $Process = Get-Process -Id ([int] $PidValue) -ErrorAction SilentlyContinue
            if ($Process) {
                Stop-Process -Id $Process.Id -Force
                Write-Host ("stopped {0} pid={1}" -f $Name, $Process.Id)
            }
            else {
                Write-Host ("{0} was not running" -f $Name)
            }
        }
        Remove-Item -LiteralPath $_.FullName -Force
    }
}

Stop-ManagedProcessByCommand "api" @("uvicorn", "context_builder.main:app")
Stop-ManagedProcessByCommand "worker-ingest" @("celery", "worker_ingest.celery_app:app")
Stop-ManagedProcessByCommand "worker-classification" @("celery", "worker_classification.celery_app:app")
Stop-ManagedProcessByCommand "worker-extraction" @("celery", "worker_extraction.celery_app:app")
