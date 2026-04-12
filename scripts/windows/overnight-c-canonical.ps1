#Requires -Version 5.1
<#
Overnight canonical capture of Claude-related state from C: into F:\c-4-26.

Scope: Claude state only (not a full machine image). Everything else on C:
will be reinstalled after the repave.

Sources, in order:
    1.  C:\.claude                              (C: root, legacy dot-folder)
    2.  C:\ClaudeBackup                         (previous backup snapshot)
    3.  C:\Users\steve\.claude                  (active Claude Code state)
    4.  C:\Users\steve\.claude-worktrees        (Claude worktrees)
    5.  C:\Users\steve\.claude.json + backups   (file-pattern mode)
    6.  C:\Users\steve\AppData\Roaming\Claude   (desktop app, ~11.5 GB)
    7.  C:\Users\steve\AppData\Roaming\Claude Code
    8.  C:\Users\steve\AppData\Local\Claude
    9.  C:\Users\steve\AppData\Local\claude-cli-nodejs
    10. wsl --shutdown                          (unlocks VHDX files)
    11. C:\wsl                                  (excluding instances\Zgent — too new)

Resumable: robocopy skips files already present at the destination with
matching size + timestamp. Safe to re-run; already-copied files are no-ops.

Run from an elevated PowerShell window that is NOT inside any WSL terminal.
All per-folder logs land in F:\c-4-26\_logs\; a summary log too.

Example:
    .\overnight-c-canonical.ps1
    .\overnight-c-canonical.ps1 -StagingRoot "F:\c-4-26"
#>
param(
    [string]$StagingRoot = "F:\c-4-26"
)

$ErrorActionPreference = "Continue"

$scriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$copyScript = Join-Path $scriptDir "copy-to-c426.ps1"

if (-not (Test-Path -LiteralPath $copyScript)) {
    Write-Error "copy-to-c426.ps1 not found next to this script: $copyScript"
    exit 1
}

if (-not (Test-Path -LiteralPath $StagingRoot)) {
    New-Item -ItemType Directory -Path $StagingRoot -Force | Out-Null
}

$logDir = Join-Path $StagingRoot "_logs"
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$summaryLog = Join-Path $logDir "overnight-${stamp}.summary.log"

function Log($msg) { $msg | Tee-Object -FilePath $summaryLog -Append }

$runStart = Get-Date
Log "Overnight canonical run started: $runStart"
Log "Staging root: $StagingRoot"
Log "Scope: Claude-related state on C: only"
Log ""

# Jobs executed before wsl --shutdown. Each is a hashtable forwarded to
# copy-to-c426.ps1 as splatted parameters.
$preWslJobs = @(
    @{ Source = "C:\.claude" },
    @{ Source = "C:\ClaudeBackup" },
    @{ Source = "C:\Users\steve\.claude" },
    @{ Source = "C:\Users\steve\.claude-worktrees" },
    @{ Source = "C:\Users\steve"; Files = @('.claude.json','.claude.json.backup*') },
    @{ Source = "C:\Users\steve\AppData\Roaming\Claude" },
    @{ Source = "C:\Users\steve\AppData\Roaming\Claude Code" },
    @{ Source = "C:\Users\steve\AppData\Local\Claude" },
    @{ Source = "C:\Users\steve\AppData\Local\claude-cli-nodejs" }
)

foreach ($job in $preWslJobs) {
    $src = $job.Source
    Log "[$(Get-Date -Format HH:mm:ss)] === $src ==="
    if (-not (Test-Path -LiteralPath $src)) {
        Log "  SKIP (not found)"
        Log ""
        continue
    }

    $params = @{ StagingRoot = $StagingRoot } + $job
    $t0 = Get-Date
    & $copyScript @params
    $rc = $LASTEXITCODE
    $dt = (Get-Date) - $t0
    Log "  exit=$rc elapsed=$([math]::Round($dt.TotalMinutes,1))m"
    Log ""
}

Log "[$(Get-Date -Format HH:mm:ss)] === wsl --shutdown ==="
& wsl.exe --shutdown 2>&1 | Tee-Object -FilePath $summaryLog -Append
Start-Sleep -Seconds 5
Log ""

Log "[$(Get-Date -Format HH:mm:ss)] === C:\wsl (excluding instances\Zgent) ==="
if (Test-Path -LiteralPath "C:\wsl") {
    $t0 = Get-Date
    & $copyScript -Source "C:\wsl" -StagingRoot $StagingRoot `
                  -Exclude @("C:\wsl\instances\Zgent")
    $rc = $LASTEXITCODE
    $dt = (Get-Date) - $t0
    Log "  exit=$rc elapsed=$([math]::Round($dt.TotalMinutes,1))m"
} else {
    Log "  SKIP (C:\wsl not found)"
}
Log ""

$runEnd  = Get-Date
$elapsed = $runEnd - $runStart
Log "Overnight run finished: $runEnd"
Log "Total elapsed: $([math]::Round($elapsed.TotalHours,2)) hours"
Log "Summary log: $summaryLog"

Write-Host ""
Write-Host "Done. Summary: $summaryLog"
