#Requires -Version 5.1
<#
Copies a supplied folder (or selected files from a folder) into F:\c-4-26,
mirroring the source path under that root with the drive letter stripped.

Uses robocopy so re-running is naturally resumable: files already at the
destination with matching size + timestamp are skipped.

Folder mode (default): recursively copies the entire source folder.
    .\copy-to-c426.ps1 -Source "C:\Users\steve\.claude"
        -> F:\c-4-26\Users\steve\.claude\...

File-pattern mode: pass -Files to copy only matching files from the top
level of -Source (non-recursive). Useful for grabbing single config files
like .claude.json and its backups without pulling the whole parent tree.
    .\copy-to-c426.ps1 -Source "C:\Users\steve" `
                       -Files @('.claude.json','.claude.json.backup*')
        -> F:\c-4-26\Users\steve\.claude.json
        -> F:\c-4-26\Users\steve\.claude.json.backup*

-Exclude: full paths of subfolders to skip (passed to robocopy /XD).
    .\copy-to-c426.ps1 -Source "C:\wsl" `
                       -Exclude @('C:\wsl\instances\Zgent')
#>
param(
    [Parameter(Mandatory=$true)][string]$Source,
    [string]$StagingRoot = "F:\c-4-26",
    [string[]]$Files     = @(),
    [string[]]$Exclude   = @()
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Source)) {
    Write-Error "Source not found: $Source"
    exit 1
}

$srcItem = Get-Item -LiteralPath $Source -Force
if (-not $srcItem.PSIsContainer) {
    Write-Error "Source must be a folder (use -Files for individual file patterns): $Source"
    exit 1
}

$srcFull = $srcItem.FullName.TrimEnd('\')
if ($srcFull -notmatch '^([A-Za-z]):\\(.*)$') {
    Write-Error "Source must be a local drive path (e.g., C:\...): $srcFull"
    exit 1
}
$rel = $Matches[2]

$dest = Join-Path $StagingRoot $rel
if (-not (Test-Path -LiteralPath $dest)) {
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
}

$logDir = Join-Path $StagingRoot "_logs"
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$leaf = Split-Path $srcFull -Leaf
if ([string]::IsNullOrWhiteSpace($leaf)) { $leaf = "root" }
$safeLeaf = $leaf -replace '[^A-Za-z0-9._-]', '_'
$logFile = Join-Path $logDir "copy-${safeLeaf}-${stamp}.log"

function Log($msg) { $msg | Tee-Object -FilePath $logFile -Append }

Log "Copy started: $(Get-Date -Format o)"
Log "  Source: $srcFull"
Log "  Dest:   $dest"
if ($Files.Count   -gt 0) { Log "  Files:  $($Files -join ', ')" }
if ($Exclude.Count -gt 0) { Log "  Exclude: $($Exclude -join ', ')" }
Log ""

# Robocopy flags:
#   /E          include subdirs (empty too) — folder mode only
#   /COPY:DAT   copy Data, Attributes, Timestamps (no ACL/ownership — avoids admin-only failures)
#   /DCOPY:DAT  same for directories
#   /R:1 /W:1   retry once, wait 1s between attempts
#   /XJ         skip junction points (AppData has loops otherwise)
#   /MT:8       8 threads
#   /NP         no per-file progress
#   /NDL        no directory list in log
#   /LOG+       append to log file
#   /TEE        also write to console
#   /XD         exclude directories (full paths)
$rcArgs = @()

if ($Files.Count -gt 0) {
    # File-pattern mode: non-recursive, only matching files at top of $srcFull.
    $rcArgs += $srcFull
    $rcArgs += $dest
    $rcArgs += $Files
    $rcArgs += @('/COPY:DAT','/DCOPY:DAT','/R:1','/W:1','/XJ','/NP','/NDL')
} else {
    # Folder mode: full recursive copy.
    $rcArgs += $srcFull
    $rcArgs += $dest
    $rcArgs += @('/E','/COPY:DAT','/DCOPY:DAT','/R:1','/W:1','/XJ','/MT:8','/NP','/NDL')
}

if ($Exclude.Count -gt 0) {
    $rcArgs += '/XD'
    $rcArgs += $Exclude
}

$rcArgs += "/LOG+:$logFile"
$rcArgs += '/TEE'

& robocopy.exe @rcArgs
$rc = $LASTEXITCODE

Log ""
Log "Copy finished: $(Get-Date -Format o)"
Log "robocopy exit code: $rc"
Log "Log: $logFile"

# Robocopy exit codes are bitflags. 0-7 are success; 8+ indicate failure.
#   0 = nothing copied (already in sync)
#   1 = files copied
#   2 = extra files/dirs at dest
#   4 = mismatches
#   8 = copy errors
#  16 = fatal error
if ($rc -ge 8) {
    Write-Warning "robocopy exit=$rc (failures) - check log"
    exit $rc
}

Write-Host ""
Write-Host "Next: verify with"
if ($Files.Count -gt 0) {
    Write-Host "  .\verify-c426.ps1 -Source `"$srcFull`" -Files @('$( $Files -join "','" )')"
} else {
    $excArg = if ($Exclude.Count -gt 0) { " -Exclude @('$( $Exclude -join "','" )')" } else { "" }
    Write-Host "  .\verify-c426.ps1 -Source `"$srcFull`"$excArg"
}
exit 0
