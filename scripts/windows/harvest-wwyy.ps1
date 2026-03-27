# Harvest WWYY (D:) to F:\WWYY
# - All of Code/
# - Backups/restore/
# - Downloads/*.pdf (root level only)
# - Downloads/RestoreTarget/
# - Downloads/Video/
# - Video/
# - Root files: .xls, .zip
param(
    [switch]$DryRun
)

$src = "D:\"
$dst = "F:\WWYY"
$logFile = "C:\DataArchive\harvest-wwyy.log"

$copied = 0
$skipped = 0
$errors = 0
$totalBytes = 0
$startTime = Get-Date

"Harvest started: $startTime" | Out-File $logFile -Encoding ASCII

function Copy-Item-Logged {
    param([string]$Source, [string]$RelPath)
    $destPath = Join-Path $dst $RelPath
    $destDir = Split-Path $destPath -Parent
    if (-not (Test-Path $destDir)) {
        if (-not $DryRun) { New-Item -ItemType Directory $destDir -Force | Out-Null }
    }
    if ($DryRun) {
        Write-Host "[DRY] $RelPath"
        $script:copied++
        return
    }
    try {
        Copy-Item -Path $Source -Destination $destPath -Force
        $script:copied++
        $script:totalBytes += (Get-Item $Source).Length
    }
    catch {
        $script:errors++
        "ERROR: $RelPath - $_" | Out-File $logFile -Append -Encoding ASCII
    }
}

# Excluded extensions (executables)
$exeExts = @('.exe','.dll','.msi','.msp','.ocx','.sys','.drv','.com','.scr','.cpl')

function Should-Skip {
    param([string]$Path)
    $ext = [System.IO.Path]::GetExtension($Path).ToLower()
    return $exeExts -contains $ext
}

# ── 1. All of Code/ ──
Write-Host "Harvesting Code/..."
Get-ChildItem -Path "D:\Code" -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
    if (Should-Skip $_.FullName) { $skipped++; return }
    $rel = $_.FullName.Substring(3)  # strip "D:\"
    Copy-Item-Logged $_.FullName $rel
    if ($copied % 5000 -eq 0 -and $copied -gt 0) {
        Write-Host "  $copied files copied, $([math]::Round($totalBytes/1GB,2)) GB"
    }
}

# ── 2. Backups/restore/ ──
Write-Host "Harvesting Backups/restore/..."
Get-ChildItem -Path "D:\Backups\restore" -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
    if (Should-Skip $_.FullName) { $skipped++; return }
    $rel = $_.FullName.Substring(3)
    Copy-Item-Logged $_.FullName $rel
}

# ── 3. Downloads/*.pdf (root only) ──
Write-Host "Harvesting Downloads/*.pdf..."
Get-ChildItem -Path "D:\Downloads\*.pdf" -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
    $rel = $_.FullName.Substring(3)
    Copy-Item-Logged $_.FullName $rel
}

# ── 4. Downloads/RestoreTarget/ ──
Write-Host "Harvesting Downloads/RestoreTarget/..."
Get-ChildItem -Path "D:\Downloads\RestoreTarget" -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
    if (Should-Skip $_.FullName) { $skipped++; return }
    $rel = $_.FullName.Substring(3)
    Copy-Item-Logged $_.FullName $rel
}

# ── 5. Downloads/Video/ ──
Write-Host "Harvesting Downloads/Video/..."
Get-ChildItem -Path "D:\Downloads\Video" -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
    $rel = $_.FullName.Substring(3)
    Copy-Item-Logged $_.FullName $rel
}

# ── 6. Video/ ──
Write-Host "Harvesting Video/..."
Get-ChildItem -Path "D:\Video" -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
    $rel = $_.FullName.Substring(3)
    Copy-Item-Logged $_.FullName $rel
}

# ── 7. Root files (.xls, .zip) ──
Write-Host "Harvesting root files..."
Get-ChildItem -Path "D:\" -File -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -match '\.(xls|zip)$' } |
    ForEach-Object {
        $rel = $_.FullName.Substring(3)
        Copy-Item-Logged $_.FullName $rel
    }

$elapsed = (Get-Date) - $startTime
$summary = @"

Harvest complete: $(Get-Date)
Drive: WWYY (D:)
Files copied: $copied
Executables skipped: $skipped
Errors: $errors
Total size: $([math]::Round($totalBytes/1GB,2)) GB
Elapsed: $([math]::Round($elapsed.TotalMinutes,1)) minutes
"@

Write-Host $summary
$summary | Out-File $logFile -Append -Encoding ASCII
