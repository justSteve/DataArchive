#Requires -Version 5.1
# Windows-native drive scanner that outputs a CSV file for DB import
# Runs elevated, writes to C:\DataArchive\scan-<drive>.csv
# Then a Python script imports the CSV into archive.db
param(
    [Parameter(Mandatory=$true)][string]$DriveLetter
)

$ErrorActionPreference = "Continue"
$DriveLetter = $DriveLetter.TrimEnd(':')
$DrivePath = "${DriveLetter}:\"
$outDir = "C:\DataArchive"
$csvFile = "$outDir\scan-${DriveLetter}.csv"
$metaFile = "$outDir\meta-${DriveLetter}.json"
$logFile = "$outDir\scan-${DriveLetter}.log"

if (-not (Test-Path $outDir)) { New-Item -ItemType Directory $outDir | Out-Null }

"Scan started: $(Get-Date)" | Out-File $logFile -Encoding ASCII

# ── Drive metadata ──
$volume = Get-Volume -DriveLetter $DriveLetter -ErrorAction SilentlyContinue
$partition = $volume | Get-Partition -ErrorAction SilentlyContinue
$disk = if ($partition) { $partition | Get-Disk -ErrorAction SilentlyContinue } else { $null }

$meta = @{
    drive_letter = $DriveLetter
    scanned_at = (Get-Date -Format o)
    hostname = $env:COMPUTERNAME
    label = $volume.FileSystemLabel
    filesystem = $volume.FileSystem
    size_bytes = $volume.Size
    free_bytes = $volume.SizeRemaining
    health = $volume.HealthStatus
    model = if ($disk) { $disk.Model } else { "Unknown" }
    serial = if ($disk) { $disk.SerialNumber.Trim() } else { "Unknown" }
    media_type = if ($disk) { "$($disk.MediaType)" } else { "Unknown" }
    bus_type = if ($disk) { "$($disk.BusType)" } else { "Unknown" }
    firmware = if ($disk) { $disk.FirmwareVersion } else { "" }
    partition_style = if ($disk) { "$($disk.PartitionStyle)" } else { "" }
    disk_number = if ($disk) { $disk.DiskNumber } else { -1 }
}

# Registry OS detection
$softwareHive = "${DrivePath}Windows\System32\config\SOFTWARE"
if (Test-Path $softwareHive -ErrorAction SilentlyContinue) {
    try {
        $hiveName = "DA_OFFLINE_$DriveLetter"
        $null = reg load "HKU\$hiveName" $softwareHive 2>&1
        $regPath = "Registry::HKU\$hiveName\Microsoft\Windows NT\CurrentVersion"
        if (Test-Path $regPath) {
            $cv = Get-ItemProperty -Path $regPath -ErrorAction SilentlyContinue
            $meta.os_product = $cv.ProductName
            $meta.os_version = $cv.DisplayVersion
            $meta.os_build = $cv.CurrentBuild
            $meta.os_edition = $cv.EditionID
            $meta.os_owner = $cv.RegisteredOwner
            if ($cv.InstallDate) {
                $meta.os_install_date = [DateTimeOffset]::FromUnixTimeSeconds($cv.InstallDate).DateTime.ToString("o")
            }
        }
        [gc]::Collect()
        Start-Sleep -Seconds 1
        $null = reg unload "HKU\$hiveName" 2>&1
    } catch {
        "Registry error: $_" | Add-Content $logFile -Encoding ASCII
        $null = reg unload "HKU\$hiveName" 2>&1
    }
}

$metaJson = $meta | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($metaFile, $metaJson, [System.Text.UTF8Encoding]::new($false))
"Metadata written" | Add-Content $logFile -Encoding ASCII

# ── File scan ──
# Write CSV: path, size_bytes, modified, created, accessed, extension, is_hidden, is_system
$writer = [System.IO.StreamWriter]::new($csvFile, $false, [System.Text.UTF8Encoding]::new($false))
$writer.WriteLine("path`tsize_bytes`tmodified`tcreated`taccessed`textension`tis_hidden`tis_system")

$count = 0
$totalSize = [long]0
$errors = 0

function Scan-Directory {
    param([string]$Path)

    try {
        $entries = [System.IO.Directory]::GetFileSystemEntries($Path)
    } catch {
        $script:errors++
        return
    }

    foreach ($entry in $entries) {
        try {
            $info = [System.IO.FileInfo]::new($entry)
            if ($info.Attributes -band [System.IO.FileAttributes]::Directory) {
                # Recurse into directory
                Scan-Directory $entry
            } else {
                $relPath = $entry.Substring($DrivePath.Length)
                $ext = $info.Extension.ToLower()
                $hidden = if ($info.Attributes -band [System.IO.FileAttributes]::Hidden) { 1 } else { 0 }
                $system = if ($info.Attributes -band [System.IO.FileAttributes]::System) { 1 } else { 0 }

                $writer.WriteLine("$relPath`t$($info.Length)`t$($info.LastWriteTime.ToString('o'))`t$($info.CreationTime.ToString('o'))`t$($info.LastAccessTime.ToString('o'))`t$ext`t$hidden`t$system")

                $script:count++
                $script:totalSize += $info.Length

                if ($script:count % 10000 -eq 0) {
                    "$($script:count) files scanned..." | Add-Content $logFile -Encoding ASCII
                    $writer.Flush()
                }
            }
        } catch {
            $script:errors++
        }
    }
}

"Starting file scan..." | Add-Content $logFile -Encoding ASCII
Scan-Directory $DrivePath

$writer.Flush()
$writer.Close()

"Scan complete: $count files, $([math]::Round($totalSize/1GB, 2)) GB, $errors errors" | Add-Content $logFile -Encoding ASCII
"Finished: $(Get-Date)" | Add-Content $logFile -Encoding ASCII
