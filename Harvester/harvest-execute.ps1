#Requires -Version 5.1
# Harvest Executor — Stage 2 of the harvest engine.
# Reads a JSONL manifest and copies files with resume, logging, and verification.
#
# Usage:
#   & "C:\myStuff\DataArchive\Harvester\harvest-execute.ps1" -Manifest "C:\myStuff\DataArchive\Harvester\manifests\harvest-WWYY.jsonl"
param(
    [Parameter(Mandatory=$true)][string]$Manifest
)

$ErrorActionPreference = "Continue"
$harvesterRoot = "C:\myStuff\DataArchive\Harvester"
$progressDir = "$harvesterRoot\progress"

if (-not (Test-Path $progressDir)) { New-Item -ItemType Directory $progressDir -Force | Out-Null }

# Derive label from manifest filename
$manifestName = [System.IO.Path]::GetFileNameWithoutExtension($Manifest)
$progressFile = "$progressDir\$manifestName.progress.jsonl"
$logFile = "$progressDir\$manifestName.log"

$startTime = Get-Date
$msg = "Harvest started: $startTime | Manifest: $Manifest"
Write-Host $msg
$msg | Out-File $logFile -Encoding UTF8

# ── Load prior progress for resume ──
$completed = @{}
if (Test-Path $progressFile) {
    Write-Host "Loading progress for resume..."
    $lineCount = 0
    foreach ($line in [System.IO.File]::ReadLines($progressFile)) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try {
            $rec = $line | ConvertFrom-Json
            if ($rec.status -eq "done") {
                $completed[$rec.src] = $true
                $lineCount++
            }
        } catch { }
    }
    Write-Host "  $lineCount files already completed, will skip"
}

# ── Read manifest, filter to copy actions ──
Write-Host "Reading manifest..."
$toCopy = [System.Collections.Generic.List[object]]::new()
$totalManifest = 0

foreach ($line in [System.IO.File]::ReadLines($Manifest)) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    $totalManifest++
    try {
        $rec = $line | ConvertFrom-Json
        if ($rec.action -eq "copy") {
            $toCopy.Add($rec)
        }
    } catch { }
}

$alreadyDone = 0
$pending = [System.Collections.Generic.List[object]]::new()
foreach ($rec in $toCopy) {
    if ($completed.ContainsKey($rec.src)) {
        $alreadyDone++
    } else {
        $pending.Add($rec)
    }
}

Write-Host "Manifest: $totalManifest entries, $($toCopy.Count) to copy, $alreadyDone already done, $($pending.Count) pending"

if ($pending.Count -eq 0) {
    Write-Host "Nothing to do — all files already copied."
    return
}

# ── Execute copies ──
$progressWriter = [System.IO.StreamWriter]::new($progressFile, $true, [System.Text.UTF8Encoding]::new($false))
$copied = 0
$errors = 0
$totalBytes = [long]0
$errorList = [System.Collections.Generic.List[string]]::new()

foreach ($rec in $pending) {
    $src = $rec.src
    $dst = $rec.dst
    $expectedSize = $rec.size
    $hash = $rec.hash

    try {
        # Create destination directory
        $dstDir = [System.IO.Path]::GetDirectoryName($dst)
        if (-not (Test-Path $dstDir)) {
            New-Item -ItemType Directory $dstDir -Force | Out-Null
        }

        # Copy
        Copy-Item -LiteralPath $src -Destination $dst -Force -ErrorAction Stop

        # Verify size
        $dstInfo = [System.IO.FileInfo]::new($dst)
        if ($dstInfo.Length -ne $expectedSize) {
            throw "Size mismatch: expected $expectedSize, got $($dstInfo.Length)"
        }

        # Log success
        $progressRec = @{ src = $src; dst = $dst; status = "done"; bytes = $dstInfo.Length }
        if ($hash) { $progressRec.hash = $hash }
        $progressWriter.WriteLine(($progressRec | ConvertTo-Json -Compress))

        $copied++
        $totalBytes += $dstInfo.Length
    }
    catch {
        $errMsg = $_.Exception.Message
        $progressRec = @{ src = $src; dst = $dst; status = "error"; error = $errMsg }
        if ($hash) { $progressRec.hash = $hash }
        $progressWriter.WriteLine(($progressRec | ConvertTo-Json -Compress))

        $errors++
        $errorList.Add("$src : $errMsg")
    }

    # Progress output
    $total = $copied + $errors
    if ($total % 500 -eq 0 -and $total -gt 0) {
        $pct = [math]::Round($total / $pending.Count * 100, 1)
        $elapsed = (Get-Date) - $startTime
        $rate = if ($elapsed.TotalMinutes -gt 0) { [math]::Round($copied / $elapsed.TotalMinutes, 0) } else { 0 }
        $gb = [math]::Round($totalBytes / 1GB, 2)
        $status = "${pct}% | ${copied} copied | ${errors} errors | ${gb} GB | ${rate} files/min"
        Write-Host $status
        $progressWriter.Flush()
    }
}

$progressWriter.Flush()
$progressWriter.Close()

$elapsed = (Get-Date) - $startTime
$summary = @"

Harvest complete: $(Get-Date)
Elapsed:      $([math]::Round($elapsed.TotalMinutes, 1)) minutes
Files copied: $copied
Errors:       $errors
Total size:   $([math]::Round($totalBytes / 1GB, 2)) GB
Progress log: $progressFile
"@

Write-Host $summary
$summary | Out-File $logFile -Append -Encoding UTF8

if ($errors -gt 0) {
    Write-Host "`nFirst 20 errors:"
    $errorList | Select-Object -First 20 | ForEach-Object { Write-Host "  $_" }
    "`nAll errors:" | Out-File $logFile -Append -Encoding UTF8
    $errorList | Out-File $logFile -Append -Encoding UTF8
}
