#Requires -Version 5.1
# Harvest Executor -Stage 2 of the harvest engine
# Reads a JSONL manifest from harvest_plan.py, copies files to staging with
# resume support, size verification, and progress logging.
#
# Usage (elevated PowerShell):
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   & C:\Users\steve\OneDrive\Tools\DataArchiver\harvest-execute.ps1 -Manifest C:\Users\steve\OneDrive\Tools\DataArchiver\manifests\harvest-WWYY.jsonl
#   & C:\Users\steve\OneDrive\Tools\DataArchiver\harvest-execute.ps1 -Manifest C:\Users\steve\OneDrive\Tools\DataArchiver\manifests\harvest-WWYY.jsonl -DryRun
param(
    [Parameter(Mandatory=$true)][string]$Manifest,
    [switch]$DryRun
)

$ErrorActionPreference = "Continue"

# -- Derive paths --
$manifestName = [System.IO.Path]::GetFileNameWithoutExtension($Manifest)
$harvesterRoot = Split-Path (Split-Path $Manifest -Parent) -Parent
$progressDir = Join-Path $harvesterRoot "progress"
$progressFile = Join-Path $progressDir "${manifestName}.progress.jsonl"

if (-not (Test-Path $progressDir)) { New-Item -ItemType Directory $progressDir -Force | Out-Null }

$startTime = Get-Date
Write-Host "Harvest executor started: $startTime"
Write-Host "Manifest: $Manifest"
if ($DryRun) { Write-Host "[DRY RUN -no files will be copied]" }

# -- Load prior progress for resume --
$done = @{}
if (Test-Path $progressFile) {
    $lines = [System.IO.File]::ReadAllLines($progressFile)
    foreach ($line in $lines) {
        $line = $line.Trim()
        if (-not $line) { continue }
        try {
            $rec = $line | ConvertFrom-Json
            if ($rec.status -eq "done") {
                $done[$rec.src] = $true
            }
        } catch {}
    }
    Write-Host "Resuming: $($done.Count) files already completed"
}

# -- Read manifest, filter to copy actions --
Write-Host "Reading manifest..."
$copyEntries = [System.Collections.Generic.List[PSCustomObject]]::new()
$totalManifest = 0

$reader = [System.IO.StreamReader]::new($Manifest)
while ($null -ne ($line = $reader.ReadLine())) {
    $totalManifest++
    $line = $line.Trim()
    if (-not $line) { continue }
    try {
        $entry = $line | ConvertFrom-Json
        if ($entry.action -eq "copy") {
            $copyEntries.Add($entry)
        }
    } catch {}
}
$reader.Close()

$toCopy = $copyEntries.Count
$alreadyDone = 0
foreach ($e in $copyEntries) {
    if ($done.ContainsKey($e.src)) { $alreadyDone++ }
}
$remaining = $toCopy - $alreadyDone
$totalCopyBytes = ($copyEntries | Where-Object { -not $done.ContainsKey($_.src) } |
    Measure-Object -Property size -Sum).Sum

Write-Host "Manifest: $totalManifest entries, $toCopy to copy, $alreadyDone already done, $remaining remaining"
Write-Host "Estimated size: $([math]::Round($totalCopyBytes/1GB, 2)) GB"
Write-Host ""

# -- Execute copies --
$copied = 0
$skipped = 0
$errors = 0
$bytesCopied = 0

$progressWriter = [System.IO.StreamWriter]::new($progressFile, $true, [System.Text.UTF8Encoding]::new($false))

foreach ($entry in $copyEntries) {
    $src = $entry.src
    $dst = $entry.dst
    $expectedSize = $entry.size

    # Resume: skip already-done files
    if ($done.ContainsKey($src)) {
        $skipped++
        continue
    }

    if ($DryRun) {
        Write-Host "[DRY] $src"
        $rec = @{ src = $src; dst = $dst; status = "dry"; bytes = $expectedSize } | ConvertTo-Json -Compress
        $progressWriter.WriteLine($rec)
        $copied++
        continue
    }

    try {
        # Create destination directory
        $dstDir = Split-Path $dst -Parent
        if (-not (Test-Path $dstDir)) {
            New-Item -ItemType Directory $dstDir -Force | Out-Null
        }

        # Use long-path prefix for paths near or over 260 chars
        $srcLP = if ($src.Length -ge 240) { "\\?\$src" } else { $src }
        $dstLP = if ($dst.Length -ge 240) { "\\?\$dst" } else { $dst }

        # Copy
        Copy-Item -LiteralPath $srcLP -Destination $dstLP -Force -ErrorAction Stop

        # Verify size
        $actualSize = (Get-Item -LiteralPath $dstLP -ErrorAction Stop).Length
        if ($actualSize -ne $expectedSize) {
            $rec = @{
                src = $src; dst = $dst; status = "error"
                error = "Size mismatch: expected $expectedSize, got $actualSize"
                bytes = $actualSize
            } | ConvertTo-Json -Compress
            $progressWriter.WriteLine($rec)
            $errors++
        } else {
            $rec = @{ src = $src; dst = $dst; status = "done"; bytes = $actualSize }
            if ($entry.hash) { $rec["hash"] = $entry.hash }
            $recJson = $rec | ConvertTo-Json -Compress
            $progressWriter.WriteLine($recJson)
            $copied++
            $bytesCopied += $actualSize
        }
    }
    catch {
        $rec = @{ src = $src; dst = $dst; status = "error"; error = $_.Exception.Message } | ConvertTo-Json -Compress
        $progressWriter.WriteLine($rec)
        $errors++
    }

    # Progress every 500 files
    $total = $copied + $errors
    if ($total -gt 0 -and $total % 500 -eq 0) {
        $elapsed = (Get-Date) - $startTime
        $rate = if ($elapsed.TotalSeconds -gt 0) { [math]::Round($total / $elapsed.TotalMinutes, 0) } else { 0 }
        $pct = [math]::Round($total / $remaining * 100, 1)
        $gbCopied = [math]::Round($bytesCopied/1GB, 2)
        $status = "$pct% - $copied copied - $errors errors - $gbCopied GB - $rate/min"
        Write-Host $status
        $progressWriter.Flush()
    }
}

$progressWriter.Flush()
$progressWriter.Close()

$elapsed = (Get-Date) - $startTime
$summary = @"

Harvest complete: $(Get-Date)
Manifest: $Manifest
Files copied: $copied
Resumed (skipped): $skipped
Errors: $errors
Total size: $([math]::Round($bytesCopied/1GB, 2)) GB
Elapsed: $([math]::Round($elapsed.TotalMinutes, 1)) minutes
Progress log: $progressFile
"@

Write-Host $summary

if ($errors -gt 0) {
    Write-Host ""
    Write-Host "Re-run this command to retry failed files."
}
