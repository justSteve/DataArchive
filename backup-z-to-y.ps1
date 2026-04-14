# Full Backup: Z: -> Y:
# Uses Robocopy for reliable, resumable copying

param(
    [string]$Source = "Z:\",
    [string]$Destination = "Y:\",
    [switch]$WhatIf,
    [switch]$SkipExisting
)

$ErrorActionPreference = "Stop"

# Verify drives exist
if (-not (Test-Path $Source)) {
    Write-Error "Source drive $Source not found!"
    exit 1
}

if (-not (Test-Path $Destination)) {
    Write-Error "Destination drive $Destination not found!"
    exit 1
}

# Create log directory
$LogDir = ".\logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogFile = "$LogDir\backup-z-to-y-$Timestamp.log"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Full Backup: $Source -> $Destination" -ForegroundColor Cyan
Write-Host "Log: $LogFile" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Robocopy parameters
$RobocopyArgs = @(
    $Source,
    $Destination,
    "/E",           # Copy subdirectories, including empty ones
    "/COPY:DAT",    # Copy Data, Attributes, and Timestamps
    "/DCOPY:DAT",   # Copy Directory timestamps
    "/R:3",         # Retry 3 times on failed copies
    "/W:5",         # Wait 5 seconds between retries
    "/MT:8",        # Multi-threaded (8 threads)
    "/V",           # Verbose output
    "/NP",          # No progress percentage (cleaner logs)
    "/LOG:$LogFile", # Log file
    "/TEE"          # Output to console AND log file
)

# Add /XO flag if skipping existing files
if ($SkipExisting) {
    $RobocopyArgs += "/XO"  # eXclude Older - skip files that exist in destination
    Write-Host "Mode: Skip files that already exist in destination" -ForegroundColor Yellow
}

# Add /L flag for WhatIf (list only, don't copy)
if ($WhatIf) {
    $RobocopyArgs += "/L"
    Write-Host "WhatIf Mode: No files will be copied (dry run)" -ForegroundColor Yellow
    Write-Host ""
}

# Calculate source size
Write-Host "Calculating source size..." -ForegroundColor Yellow
$SourceSize = (Get-ChildItem -Path $Source -Recurse -File -ErrorAction SilentlyContinue |
               Measure-Object -Property Length -Sum).Sum
$SourceSizeGB = [math]::Round($SourceSize / 1GB, 2)
Write-Host "Source size: $SourceSizeGB GB" -ForegroundColor Green
Write-Host ""

# Start backup
$StartTime = Get-Date
Write-Host "Starting backup at $StartTime..." -ForegroundColor Green
Write-Host ""

# Run Robocopy
& robocopy @RobocopyArgs

$ExitCode = $LASTEXITCODE
$EndTime = Get-Date
$Duration = $EndTime - $StartTime

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Backup completed at $EndTime" -ForegroundColor Cyan
Write-Host "Duration: $($Duration.ToString('hh\:mm\:ss'))" -ForegroundColor Cyan
Write-Host "Exit Code: $ExitCode" -ForegroundColor Cyan
Write-Host "Log: $LogFile" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Robocopy exit codes:
# 0 = No files copied (no changes)
# 1 = Files copied successfully
# 2 = Extra files or directories detected (some files in dest but not source)
# 4 = Some mismatched files or directories
# 8 = Some files or directories could not be copied (copy errors)
# 16 = Serious error (Robocopy did not copy any files)

if ($ExitCode -ge 8) {
    Write-Host "WARNING: Some errors occurred during backup. Check log file." -ForegroundColor Red
    exit 1
} elseif ($ExitCode -eq 0) {
    Write-Host "No changes detected - backup already up to date." -ForegroundColor Yellow
} else {
    Write-Host "Backup completed successfully!" -ForegroundColor Green
}
