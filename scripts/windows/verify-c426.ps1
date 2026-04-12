#Requires -Version 5.1
<#
Verifies a folder (or selected files from a folder) previously copied to
F:\c-4-26 by copy-to-c426.ps1.

Walks the source tree and confirms every expected file exists at the
mirrored destination with matching length. Use -Hash for SHA256 comparison.

-Files:   restrict verification to the matching file patterns at the top
          level of -Source (mirrors copy-to-c426.ps1's -Files mode).
-Exclude: full paths of subfolders to ignore when walking source
          (mirrors copy-to-c426.ps1's -Exclude so skipped paths don't
          show up as "missing at dest").

Exit 0 on clean verification, 1 on any discrepancy.

Examples:
    .\verify-c426.ps1 -Source "C:\Users\steve\.claude"
    .\verify-c426.ps1 -Source "C:\wsl" -Exclude @('C:\wsl\instances\Zgent')
    .\verify-c426.ps1 -Source "C:\Users\steve" `
                      -Files @('.claude.json','.claude.json.backup*')
    .\verify-c426.ps1 -Source "C:\Users\steve\.claude" -Hash
#>
param(
    [Parameter(Mandatory=$true)][string]$Source,
    [string]$StagingRoot = "F:\c-4-26",
    [string[]]$Files     = @(),
    [string[]]$Exclude   = @(),
    [switch]$Hash
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Source)) {
    Write-Error "Source not found: $Source"
    exit 1
}

$srcItem = Get-Item -LiteralPath $Source -Force
if (-not $srcItem.PSIsContainer) {
    Write-Error "Source must be a folder: $Source"
    exit 1
}

$srcFull = $srcItem.FullName.TrimEnd('\')
if ($srcFull -notmatch '^([A-Za-z]):\\(.*)$') {
    Write-Error "Source must be a local drive path: $srcFull"
    exit 1
}
$rel = $Matches[2]

$dest = Join-Path $StagingRoot $rel
if (-not (Test-Path -LiteralPath $dest)) {
    Write-Error "Destination not found: $dest"
    exit 1
}

$logDir = Join-Path $StagingRoot "_logs"
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$leaf = Split-Path $srcFull -Leaf
if ([string]::IsNullOrWhiteSpace($leaf)) { $leaf = "root" }
$safeLeaf = $leaf -replace '[^A-Za-z0-9._-]', '_'
$logFile = Join-Path $logDir "verify-${safeLeaf}-${stamp}.log"

function Log($msg) { $msg | Tee-Object -FilePath $logFile -Append }

Log "Verify started: $(Get-Date -Format o)"
Log "  Source: $srcFull"
Log "  Dest:   $dest"
Log ("  Mode:   " + $(if ($Hash) { "size + sha256" } else { "size only" }))
if ($Files.Count   -gt 0) { Log "  Files:   $($Files -join ', ')" }
if ($Exclude.Count -gt 0) { Log "  Exclude: $($Exclude -join ', ')" }
Log ""

# Normalize excludes for prefix matching (lowercased, trimmed, trailing sep).
$excludeNormalized = @()
foreach ($e in $Exclude) {
    $ne = $e.TrimEnd('\').ToLowerInvariant() + '\'
    $excludeNormalized += $ne
}

function Test-Excluded($fullPath) {
    if ($excludeNormalized.Count -eq 0) { return $false }
    $p = $fullPath.ToLowerInvariant()
    foreach ($ex in $excludeNormalized) {
        if ($p.StartsWith($ex)) { return $true }
    }
    return $false
}

$missing      = [System.Collections.Generic.List[string]]::new()
$sizeMismatch = [System.Collections.Generic.List[string]]::new()
$hashMismatch = [System.Collections.Generic.List[string]]::new()
$srcErrors = 0
$dstErrors = 0
$okFiles = 0
$totalBytes = [long]0

# Build source enumeration: either matching files at top of $srcFull
# (file-pattern mode) or the full recursive tree.
# Note: -Include on Get-ChildItem is unreliable without -Recurse on PS 5.1,
# so we enumerate top-level files and match -like against the pattern list.
if ($Files.Count -gt 0) {
    $srcEnumerator = Get-ChildItem -LiteralPath $srcFull -File -Force `
        -ErrorAction SilentlyContinue | Where-Object {
            $name = $_.Name
            foreach ($pat in $Files) {
                if ($name -like $pat) { return $true }
            }
            return $false
        }
} else {
    $srcEnumerator = Get-ChildItem -LiteralPath $srcFull -Recurse -File -Force `
        -ErrorAction SilentlyContinue
}

$srcEnumerator | ForEach-Object {
    $srcFile = $_

    if (Test-Excluded $srcFile.FullName) { return }

    $relFile = $srcFile.FullName.Substring($srcFull.Length).TrimStart('\')
    $dstFile = Join-Path $dest $relFile

    if (-not (Test-Path -LiteralPath $dstFile)) {
        $missing.Add($relFile) | Out-Null
        return
    }

    try {
        $dstInfo = Get-Item -LiteralPath $dstFile -Force -ErrorAction Stop
    } catch {
        $dstErrors++
        return
    }

    if ($dstInfo.Length -ne $srcFile.Length) {
        $sizeMismatch.Add("$relFile  src=$($srcFile.Length) dst=$($dstInfo.Length)") | Out-Null
        return
    }

    if ($Hash -and $srcFile.Length -gt 0) {
        try {
            $srcHash = (Get-FileHash -LiteralPath $srcFile.FullName -Algorithm SHA256 -ErrorAction Stop).Hash
            $dstHash = (Get-FileHash -LiteralPath $dstFile -Algorithm SHA256 -ErrorAction Stop).Hash
            if ($srcHash -ne $dstHash) {
                $hashMismatch.Add("$relFile  src=$srcHash dst=$dstHash") | Out-Null
                return
            }
        } catch {
            $srcErrors++
            return
        }
    }

    $okFiles++
    $totalBytes += $srcFile.Length

    if ($okFiles % 1000 -eq 0) {
        Write-Host "  checked $okFiles files, $([math]::Round($totalBytes/1GB, 2)) GB..."
    }
}

Log ""
Log "-- Summary --"
Log "OK:              $okFiles files ($([math]::Round($totalBytes/1GB, 3)) GB)"
Log "Missing at dst:  $($missing.Count)"
Log "Size mismatch:   $($sizeMismatch.Count)"
if ($Hash) { Log "Hash mismatch:   $($hashMismatch.Count)" }
Log "Src read errors: $srcErrors"
Log "Dst read errors: $dstErrors"

if ($missing.Count -gt 0) {
    Log ""
    Log "-- Missing files (first 50) --"
    $missing | Select-Object -First 50 | ForEach-Object { Log "  $_" }
    if ($missing.Count -gt 50) { Log "  ... and $($missing.Count - 50) more" }
}

if ($sizeMismatch.Count -gt 0) {
    Log ""
    Log "-- Size mismatches (first 50) --"
    $sizeMismatch | Select-Object -First 50 | ForEach-Object { Log "  $_" }
    if ($sizeMismatch.Count -gt 50) { Log "  ... and $($sizeMismatch.Count - 50) more" }
}

if ($Hash -and $hashMismatch.Count -gt 0) {
    Log ""
    Log "-- Hash mismatches (first 50) --"
    $hashMismatch | Select-Object -First 50 | ForEach-Object { Log "  $_" }
    if ($hashMismatch.Count -gt 50) { Log "  ... and $($hashMismatch.Count - 50) more" }
}

Log ""
Log "Verify finished: $(Get-Date -Format o)"
Log "Log: $logFile"

$fail = ($missing.Count + $sizeMismatch.Count + $hashMismatch.Count + $srcErrors + $dstErrors) -gt 0
if ($fail) {
    Write-Warning "Verification found issues - see $logFile"
    exit 1
}

Write-Host ""
Write-Host "VERIFIED: $okFiles files, $([math]::Round($totalBytes/1GB, 3)) GB match"
exit 0
