#Requires -Version 5.1
# Build a harvest progress file from an existing staging directory.
# Hashes every file and writes a progress JSONL compatible with harvest_plan.py
# dedup, so subsequent drives skip files already staged.
#
# Usage (elevated PowerShell):
#   & C:\Users\steve\OneDrive\Tools\DataArchiver\scripts\windows\build-progress-from-staging.ps1 -StagingPath F:\WWYY -Label WWYY
param(
    [Parameter(Mandatory=$true)][string]$StagingPath,
    [Parameter(Mandatory=$true)][string]$Label
)

$ErrorActionPreference = "Continue"

$harvesterRoot = "C:\Users\steve\OneDrive\Tools\DataArchiver\Harvester"
$progressDir = Join-Path $harvesterRoot "progress"
$progressFile = Join-Path $progressDir "harvest-${Label}.progress.jsonl"

if (-not (Test-Path $progressDir)) { New-Item -ItemType Directory $progressDir -Force | Out-Null }

$startTime = Get-Date
Write-Host "Building progress file from staged files in $StagingPath"
Write-Host "Output: $progressFile"

# Count files first
Write-Host "Counting files..."
$allFiles = @(Get-ChildItem -Path $StagingPath -Recurse -File -Force -ErrorAction SilentlyContinue)
$totalFiles = $allFiles.Count
Write-Host "Found $totalFiles files to hash"

$hashed = 0
$errors = 0
$totalBytes = 0

$writer = [System.IO.StreamWriter]::new($progressFile, $false, [System.Text.UTF8Encoding]::new($false))

foreach ($file in $allFiles) {
    try {
        $hash = (Get-FileHash -Path $file.FullName -Algorithm SHA256 -ErrorAction Stop).Hash
        $rec = @{
            src = ""
            dst = $file.FullName
            status = "done"
            bytes = $file.Length
            hash = $hash
        } | ConvertTo-Json -Compress
        $writer.WriteLine($rec)
        $hashed++
        $totalBytes += $file.Length
    }
    catch {
        $errors++
        $rec = @{
            dst = $file.FullName
            status = "error"
            error = $_.Exception.Message
        } | ConvertTo-Json -Compress
        $writer.WriteLine($rec)
    }

    if ($hashed % 500 -eq 0 -and $hashed -gt 0) {
        $elapsed = (Get-Date) - $startTime
        $rate = if ($elapsed.TotalSeconds -gt 0) { [math]::Round($hashed / $elapsed.TotalMinutes, 0) } else { 0 }
        $pct = [math]::Round(($hashed + $errors) / $totalFiles * 100, 1)
        $status = "${pct}% | ${hashed} hashed | ${rate}/min | $([math]::Round($totalBytes/1GB,2)) GB"
        Write-Host $status
        $writer.Flush()
    }
}

$writer.Flush()
$writer.Close()

$elapsed = (Get-Date) - $startTime
$summary = @"

Progress file built: $(Get-Date)
Source: $StagingPath
Files hashed: $hashed
Errors: $errors
Total size: $([math]::Round($totalBytes/1GB, 2)) GB
Elapsed: $([math]::Round($elapsed.TotalMinutes, 1)) minutes
Output: $progressFile
"@

Write-Host $summary
