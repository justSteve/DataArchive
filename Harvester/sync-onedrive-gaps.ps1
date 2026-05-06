#Requires -Version 5.1
# Finds files that exist in OneDrive cloud but not on C:.
# Downloads them to W:\OneDrive-archive\.
#
# Prerequisites:
#   1. rclone installed:  winget install rclone
#   2. OneDrive remote configured:  rclone config
#      (choose "onedrive", follow browser auth, name it "onedrive")
#
# Usage:
#   .\sync-onedrive-gaps.ps1              # dry run — just list what's missing
#   .\sync-onedrive-gaps.ps1 -Download    # actually download

param(
    [switch]$Download
)

$ErrorActionPreference = "Continue"

$remoteName = "onedrive"
$localOneDrive = "$env:USERPROFILE\OneDrive"
$destRoot = "W:\OneDrive-archive"
$candidateList = "\\wsl.localhost\Ubuntu\tmp\onedrive-cloud-only.txt"
$logFile = "\\wsl.localhost\Ubuntu\root\projects\DataArchive\Harvester\progress\onedrive-gaps.log"

# --- Pre-flight ---
if (-not (Get-Command rclone -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: rclone not found. Install: winget install rclone"
    Write-Host "Then configure: rclone config  (add remote named 'onedrive', type 'onedrive')"
    exit 1
}

# Check remote is configured
$remotes = rclone listremotes 2>&1
if ($remotes -notmatch "$remoteName`:") {
    Write-Host "ERROR: rclone remote '$remoteName' not configured."
    Write-Host "Run: rclone config"
    Write-Host "  Choose 'n' new remote, name it 'onedrive', type 'onedrive'"
    Write-Host "  Follow the browser auth flow"
    exit 1
}

if (-not (Test-Path $candidateList)) {
    Write-Host "ERROR: candidate list not found at $candidateList"
    exit 1
}

# --- Load candidates ---
$candidates = Get-Content $candidateList | Where-Object { $_ -ne "" }
Write-Host "Candidates from old drive placeholders: $($candidates.Count)"

# --- Check what's already on C: ---
$missing = [System.Collections.Generic.List[string]]::new()
$alreadyLocal = 0

foreach ($rel in $candidates) {
    $localPath = Join-Path $localOneDrive $rel
    if (Test-Path -LiteralPath $localPath) {
        $alreadyLocal++
    } else {
        $missing.Add($rel)
    }
}

Write-Host "Already on C: $alreadyLocal"
Write-Host "Not on C:     $($missing.Count)"
Write-Host ""

if ($missing.Count -eq 0) {
    Write-Host "Nothing to do."
    exit 0
}

# --- Check which missing files actually exist in OneDrive cloud ---
Write-Host "Checking which files still exist in OneDrive cloud..."
Write-Host "(This queries the API — may take a few minutes for $($missing.Count) files)"
Write-Host ""

$existsInCloud = [System.Collections.Generic.List[string]]::new()
$gone = 0
$checked = 0
$errors = 0

# Batch by directory to reduce API calls
$dirs = @{}
foreach ($rel in $missing) {
    $parent = [System.IO.Path]::GetDirectoryName($rel) -replace '\\', '/'
    if (-not $dirs.ContainsKey($parent)) {
        $dirs[$parent] = [System.Collections.Generic.List[string]]::new()
    }
    $dirs[$parent].Add($rel)
}

Write-Host "Scanning $($dirs.Count) directories..."

foreach ($dir in $dirs.Keys | Sort-Object) {
    $remotePath = "${remoteName}:${dir}"
    try {
        $listing = rclone lsf "$remotePath" --files-only 2>$null
        if ($null -eq $listing) { $listing = @() }
        $cloudFiles = @{}
        foreach ($f in $listing) {
            $cloudFiles[$f.TrimEnd('/')] = $true
        }

        foreach ($rel in $dirs[$dir]) {
            $fname = [System.IO.Path]::GetFileName($rel)
            if ($cloudFiles.ContainsKey($fname)) {
                $existsInCloud.Add($rel)
            } else {
                $gone++
            }
            $checked++
        }
    }
    catch {
        foreach ($rel in $dirs[$dir]) {
            $errors++
            $checked++
        }
    }

    if ($checked % 1000 -lt $dirs[$dir].Count) {
        Write-Host "  checked $checked / $($missing.Count) — found $($existsInCloud.Count) in cloud, $gone deleted"
    }
}

Write-Host ""
Write-Host "=== Results ==="
Write-Host "  Still in OneDrive cloud: $($existsInCloud.Count)"
Write-Host "  Deleted from OneDrive:   $gone"
Write-Host "  Errors:                  $errors"
Write-Host ""

if ($existsInCloud.Count -eq 0) {
    Write-Host "No downloadable files found."
    exit 0
}

# Save the gap list
$gapCsv = Join-Path ([System.IO.Path]::GetDirectoryName($logFile)) "onedrive-gaps.csv"
"path" | Out-File $gapCsv -Encoding UTF8
$existsInCloud | Out-File $gapCsv -Append -Encoding UTF8
Write-Host "Gap list saved: $gapCsv"

if (-not $Download) {
    Write-Host ""
    Write-Host "Dry run complete. To download, re-run with -Download"
    exit 0
}

# --- Download ---
Write-Host ""
Write-Host "Downloading $($existsInCloud.Count) files to $destRoot ..."
if (-not (Test-Path $destRoot)) { New-Item -ItemType Directory $destRoot -Force | Out-Null }

$downloaded = 0
$dlErrors = 0
$dlBytes = [long]0

foreach ($rel in $existsInCloud) {
    $remotePath = "${remoteName}:${rel}"
    $localDest = Join-Path $destRoot $rel
    $localDir = [System.IO.Path]::GetDirectoryName($localDest)

    if (-not (Test-Path $localDir)) {
        New-Item -ItemType Directory $localDir -Force | Out-Null
    }

    try {
        rclone copyto "$remotePath" "$localDest" --no-traverse 2>$null
        if (Test-Path $localDest) {
            $sz = (Get-Item -LiteralPath $localDest).Length
            $dlBytes += $sz
            $downloaded++
        } else {
            $dlErrors++
        }
    }
    catch {
        $dlErrors++
    }

    $total = $downloaded + $dlErrors
    if ($total % 500 -eq 0 -and $total -gt 0) {
        $gb = [math]::Round($dlBytes / 1GB, 2)
        Write-Host "  $total / $($existsInCloud.Count) — $downloaded OK, $dlErrors errors, $gb GB"
    }
}

$gb = [math]::Round($dlBytes / 1GB, 2)
Write-Host ""
Write-Host "=== Download Complete ==="
Write-Host "  Downloaded: $downloaded files ($gb GB)"
Write-Host "  Errors:     $dlErrors"
Write-Host "  Location:   $destRoot"
