#Requires -Version 5.1
# Hash all files on a drive with SHA256 for cross-drive deduplication
# Outputs CSV to C:\DataArchive\hash-<drive>.csv
# Can run two instances simultaneously (one per dock bay)
param(
    [Parameter(Mandatory=$true)][string]$DriveLetter,
    [int]$MaxSizeMB = 2048  # Skip files larger than this (default 2GB)
)

$ErrorActionPreference = "Continue"
$DriveLetter = $DriveLetter.TrimEnd(':')
$DrivePath = "${DriveLetter}:\"
$outDir = "C:\DataArchive"
$csvFile = "$outDir\hash-${DriveLetter}.csv"
$logFile = "$outDir\hash-${DriveLetter}.log"
$progressFile = "$outDir\hash-${DriveLetter}.progress"
$maxBytes = $MaxSizeMB * 1MB

if (-not (Test-Path $outDir)) { New-Item -ItemType Directory $outDir | Out-Null }

$startTime = Get-Date
"Hash started: $startTime" | Out-File $logFile -Encoding ASCII

# ── Header ──
"path,size_bytes,sha256" | Out-File $csvFile -Encoding UTF8

# ── Count files first for progress tracking ──
Write-Host "Counting files on ${DrivePath}..."
$allFiles = @(Get-ChildItem -Path $DrivePath -Recurse -File -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Length -gt 0 -and $_.Length -le $maxBytes })
$totalFiles = $allFiles.Count
Write-Host "Found $totalFiles hashable files (non-zero, under ${MaxSizeMB}MB)"
"Total files to hash: $totalFiles" | Out-File $logFile -Append -Encoding ASCII

$hashed = 0
$skipped = 0
$errors = 0
$batchSize = 500
$batch = [System.Collections.Generic.List[string]]::new()

foreach ($file in $allFiles) {
    try {
        $hash = (Get-FileHash -Path $file.FullName -Algorithm SHA256 -ErrorAction Stop).Hash
        $escapedPath = $file.FullName -replace '"','""'
        $batch.Add("`"$escapedPath`",$($file.Length),$hash")
        $hashed++
    }
    catch {
        $skipped++
        $errors++
    }

    # Flush batch to disk periodically
    if ($batch.Count -ge $batchSize) {
        $batch | Out-File $csvFile -Append -Encoding UTF8
        $batch.Clear()

        # Progress update
        $pct = [math]::Round(($hashed + $skipped) / $totalFiles * 100, 1)
        $elapsed = (Get-Date) - $startTime
        $rate = if ($elapsed.TotalSeconds -gt 0) { [math]::Round($hashed / $elapsed.TotalMinutes, 0) } else { 0 }
        $status = "${DriveLetter}: ${pct}% | ${hashed} hashed | ${rate}/min | $([math]::Round($elapsed.TotalMinutes,1))m elapsed"
        Write-Host $status
        $status | Out-File $progressFile -Encoding ASCII
    }
}

# Flush remaining
if ($batch.Count -gt 0) {
    $batch | Out-File $csvFile -Append -Encoding UTF8
}

$elapsed = (Get-Date) - $startTime
$summary = @"
Hash complete: $(Get-Date)
Drive: ${DriveLetter}:
Files hashed: $hashed
Errors/skipped: $errors
Elapsed: $([math]::Round($elapsed.TotalMinutes,1)) minutes
Output: $csvFile
"@

Write-Host $summary
$summary | Out-File $logFile -Append -Encoding ASCII
Remove-Item $progressFile -ErrorAction SilentlyContinue
