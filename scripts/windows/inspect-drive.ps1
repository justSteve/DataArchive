#Requires -Version 5.1
<#
.SYNOPSIS
    Deep drive inspection companion for DataArchive.
    Runs natively on Windows — no WSL permission barriers.

.DESCRIPTION
    Inspects a drive letter thoroughly and outputs JSON to a specified file.
    Designed to be called from WSL via:
        powershell.exe -ExecutionPolicy Bypass -File inspect-drive.ps1 -DriveLetter G -OutFile /path/to/output.json

.PARAMETER DriveLetter
    Drive letter to inspect (e.g., G)

.PARAMETER OutFile
    Path to write JSON results. Supports both Windows and UNC paths.
    If omitted, writes to stdout.
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$DriveLetter,

    [Parameter(Mandatory=$false)]
    [string]$OutFile
)

$ErrorActionPreference = "Continue"
$DriveLetter = $DriveLetter.TrimEnd(':')
$DrivePath = "${DriveLetter}:\"

# ─── Self-elevate if not admin ─────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    # Elevated processes can't access \\wsl.localhost paths, so:
    # 1. Copy script to Windows temp
    # 2. Run elevated from there
    # 3. Copy results back
    $tempDir = Join-Path $env:TEMP "DataArchive"
    if (-not (Test-Path $tempDir)) { New-Item -ItemType Directory $tempDir | Out-Null }
    $tempScript = Join-Path $tempDir "inspect-drive.ps1"
    $tempOut = Join-Path $tempDir "inspect-$DriveLetter.json"
    $tempLog = Join-Path $tempDir "inspect-$DriveLetter.log"

    Copy-Item $MyInvocation.MyCommand.Path $tempScript -Force

    $argString = "-ExecutionPolicy Bypass -File `"$tempScript`" -DriveLetter $DriveLetter -OutFile `"$tempOut`""
    Start-Process powershell.exe -Verb RunAs -ArgumentList $argString -Wait

    # Copy result from Windows temp to requested output location
    if (Test-Path $tempOut) {
        if ($OutFile) {
            Copy-Item $tempOut $OutFile -Force
            Write-Host "Results copied to: $OutFile"
        } else {
            Get-Content $tempOut -Raw
        }
        Remove-Item $tempOut -Force
    } else {
        Write-Host "ERROR: Elevated process did not produce output." -ForegroundColor Red
        Write-Host "Temp script: $tempScript" -ForegroundColor Yellow
        Write-Host "Expected output: $tempOut" -ForegroundColor Yellow
        if (Test-Path $tempLog) {
            Write-Host "Log:" -ForegroundColor Yellow
            Get-Content $tempLog
        }
    }
    exit
}

# ─── Helpers ───────────────────────────────────────────────

function Safe-GetChildItem {
    param([string]$Path, [int]$Depth = 0, [switch]$File, [switch]$Directory)
    try {
        $params = @{ Path = $Path; ErrorAction = 'SilentlyContinue' }
        if ($File) { $params['File'] = $true }
        if ($Directory) { $params['Directory'] = $true }
        if ($Depth -gt 0) { $params['Depth'] = $Depth }
        Get-ChildItem @params
    } catch { @() }
}

function Get-FolderSizeSafe {
    param([string]$Path)
    try {
        $items = Get-ChildItem -Path $Path -Recurse -File -ErrorAction SilentlyContinue
        ($items | Measure-Object -Property Length -Sum).Sum
    } catch { 0 }
}

# ─── Start collection ─────────────────────────────────────

$result = @{
    drive_letter    = $DriveLetter
    inspected_at    = (Get-Date -Format o)
    hostname        = $env:COMPUTERNAME
    sections        = @{}
    errors          = @()
}

# ─── 1. Physical disk info ─────────────────────────────────

try {
    $volume = Get-Volume -DriveLetter $DriveLetter -ErrorAction Stop
    $partition = $volume | Get-Partition -ErrorAction SilentlyContinue
    $disk = if ($partition) { $partition | Get-Disk -ErrorAction SilentlyContinue } else { $null }

    $result.sections.volume = @{
        label           = $volume.FileSystemLabel
        filesystem      = $volume.FileSystem
        size_bytes      = $volume.Size
        free_bytes      = $volume.SizeRemaining
        health          = $volume.HealthStatus
        drive_type      = $volume.DriveType
    }

    if ($disk) {
        $result.sections.disk = @{
            model           = $disk.Model
            serial          = $disk.SerialNumber
            media_type      = $disk.MediaType
            bus_type        = $disk.BusType
            size_bytes      = $disk.Size
            partition_style = $disk.PartitionStyle
            firmware        = $disk.FirmwareVersion
            disk_number     = $disk.DiskNumber
            is_boot         = $disk.IsBoot
            is_system       = $disk.IsSystem
        }
    }

    # SMART / reliability
    if ($disk) {
        try {
            $rel = Get-StorageReliabilityCounter -PhysicalDisk (Get-PhysicalDisk | Where-Object { $_.DeviceId -eq $disk.DiskNumber }) -ErrorAction Stop
            $result.sections.smart = @{
                temperature     = $rel.Temperature
                wear            = $rel.Wear
                read_errors     = $rel.ReadErrorsTotal
                write_errors    = $rel.WriteErrorsTotal
                power_on_hours  = $rel.PowerOnHours
                start_stop      = $rel.StartStopCycleCount
            }
        } catch {
            $result.errors += "SMART data unavailable: $_"
        }
    }
} catch {
    $result.errors += "Volume/disk detection failed: $_"
}

# ─── 2. OS detection via registry hive ─────────────────────

$softwareHive = "${DrivePath}Windows\System32\config\SOFTWARE"
if (Test-Path $softwareHive -ErrorAction SilentlyContinue) {
    try {
        # Load offline hive
        $hiveName = "DA_OFFLINE_$DriveLetter"
        $null = reg load "HKU\$hiveName" $softwareHive 2>&1

        $regPath = "Registry::HKU\$hiveName\Microsoft\Windows NT\CurrentVersion"
        if (Test-Path $regPath) {
            $cv = Get-ItemProperty -Path $regPath -ErrorAction SilentlyContinue
            $result.sections.os = @{
                product_name    = $cv.ProductName
                display_version = $cv.DisplayVersion
                current_build   = $cv.CurrentBuild
                edition_id      = $cv.EditionID
                install_date    = if ($cv.InstallDate) {
                    [DateTimeOffset]::FromUnixTimeSeconds($cv.InstallDate).DateTime.ToString("o")
                } else { $null }
                registered_owner = $cv.RegisteredOwner
                registered_org  = $cv.RegisteredOrganization
                build_lab       = $cv.BuildLabEx
                ubr             = $cv.UBR
            }
        }

        # Installed software from registry
        $uninstallPaths = @(
            "Registry::HKU\$hiveName\Microsoft\Windows\CurrentVersion\Uninstall",
            "Registry::HKU\$hiveName\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"
        )
        $installedSoftware = @()
        foreach ($upath in $uninstallPaths) {
            if (Test-Path $upath) {
                Get-ChildItem $upath -ErrorAction SilentlyContinue | ForEach-Object {
                    $props = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue
                    if ($props.DisplayName) {
                        $installedSoftware += @{
                            name        = $props.DisplayName
                            version     = $props.DisplayVersion
                            publisher   = $props.Publisher
                            install_date = $props.InstallDate
                        }
                    }
                }
            }
        }
        $result.sections.installed_software = $installedSoftware

        # Unload hive
        [gc]::Collect()
        $null = reg unload "HKU\$hiveName" 2>&1
    } catch {
        $result.errors += "Registry hive read failed: $_"
        # Try to unload anyway
        $null = reg unload "HKU\$hiveName" 2>&1
    }
}

# ─── 3. User profiles ──────────────────────────────────────

$usersPath = "${DrivePath}Users"
if (Test-Path $usersPath) {
    $profiles = @()
    $skipProfiles = @('All Users', 'Default', 'Default User', 'Public', 'desktop.ini')

    Get-ChildItem $usersPath -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notin $skipProfiles } |
        ForEach-Object {
            $profilePath = $_.FullName
            $profileName = $_.Name

            $profile = @{
                username = $profileName
                folders  = @{}
            }

            # Key user folders and their contents summary
            $userFolders = @('Desktop', 'Documents', 'Downloads', 'Pictures', 'Music', 'Videos',
                            'OneDrive', 'Dropbox', 'Google Drive', '.ssh', 'AppData')

            foreach ($folder in $userFolders) {
                $folderPath = Join-Path $profilePath $folder
                if (Test-Path $folderPath -ErrorAction SilentlyContinue) {
                    $files = Get-ChildItem $folderPath -Recurse -File -ErrorAction SilentlyContinue
                    $fileCount = ($files | Measure-Object).Count
                    $totalSize = ($files | Measure-Object -Property Length -Sum).Sum

                    # Get top-level items for context
                    $topItems = Get-ChildItem $folderPath -ErrorAction SilentlyContinue |
                        Select-Object -First 50 |
                        ForEach-Object {
                            @{
                                name = $_.Name
                                is_dir = $_.PSIsContainer
                                size = if (-not $_.PSIsContainer) { $_.Length } else { $null }
                                modified = $_.LastWriteTime.ToString("o")
                            }
                        }

                    $profile.folders[$folder] = @{
                        file_count = $fileCount
                        total_size = $totalSize
                        top_items  = @($topItems)
                    }
                }
            }

            # Recent documents / activity traces
            $recentPath = Join-Path $profilePath "AppData\Roaming\Microsoft\Windows\Recent"
            if (Test-Path $recentPath -ErrorAction SilentlyContinue) {
                $recentFiles = Get-ChildItem $recentPath -File -ErrorAction SilentlyContinue |
                    Sort-Object LastWriteTime -Descending |
                    Select-Object -First 30 |
                    ForEach-Object { @{ name = $_.BaseName; accessed = $_.LastWriteTime.ToString("o") } }
                $profile.recent_files = @($recentFiles)
            }

            $profiles += $profile
        }

    $result.sections.user_profiles = $profiles
}

# ─── 4. Interesting top-level folders ───────────────────────

$topLevel = Get-ChildItem $DrivePath -ErrorAction SilentlyContinue | ForEach-Object {
    @{
        name     = $_.Name
        is_dir   = $_.PSIsContainer
        size     = if (-not $_.PSIsContainer) { $_.Length } else { $null }
        modified = $_.LastWriteTime.ToString("o")
        hidden   = $_.Attributes -band [IO.FileAttributes]::Hidden
    }
}
$result.sections.top_level = @($topLevel)

# ─── 5. File type census (sampled from key areas) ──────────

$censusAreas = @("${DrivePath}Users", "${DrivePath}Documents and Settings")
$extensionMap = @{}
foreach ($area in $censusAreas) {
    if (Test-Path $area) {
        Get-ChildItem $area -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
            $ext = if ($_.Extension) { $_.Extension.ToLower() } else { "(none)" }
            if (-not $extensionMap.ContainsKey($ext)) {
                $extensionMap[$ext] = @{ count = 0; size = 0 }
            }
            $extensionMap[$ext].count++
            $extensionMap[$ext].size += $_.Length
        }
    }
}
# Convert to sorted list
$result.sections.file_census = $extensionMap.GetEnumerator() |
    Sort-Object { $_.Value.count } -Descending |
    Select-Object -First 50 |
    ForEach-Object { @{ extension = $_.Key; count = $_.Value.count; total_size = $_.Value.size } }

# ─── 6. Date archaeology ───────────────────────────────────

# Find oldest and newest files in user areas to establish era
$dateFiles = @()
foreach ($area in $censusAreas) {
    if (Test-Path $area) {
        $dateFiles += Get-ChildItem $area -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime.Year -gt 1980 }
    }
}

if ($dateFiles.Count -gt 0) {
    $sorted = $dateFiles | Sort-Object LastWriteTime
    $oldest = $sorted | Select-Object -First 10 | ForEach-Object {
        @{ path = $_.FullName.Replace($DrivePath, ''); date = $_.LastWriteTime.ToString("o"); size = $_.Length }
    }
    $newest = $sorted | Select-Object -Last 10 | ForEach-Object {
        @{ path = $_.FullName.Replace($DrivePath, ''); date = $_.LastWriteTime.ToString("o"); size = $_.Length }
    }

    # Year distribution
    $yearDist = $dateFiles | Group-Object { $_.LastWriteTime.Year } |
        Sort-Object Name |
        ForEach-Object { @{ year = [int]$_.Name; file_count = $_.Count } }

    $result.sections.date_archaeology = @{
        oldest_files    = @($oldest)
        newest_files    = @($newest)
        year_distribution = @($yearDist)
        total_sampled   = $dateFiles.Count
    }
}

# ─── 7. Non-Windows drives: look for anything ──────────────

if (-not (Test-Path "${DrivePath}Windows")) {
    # Not a Windows boot drive — scan everything at top level more aggressively
    $result.sections.non_windows = $true

    # Full top-level directory sizes
    $dirSizes = Get-ChildItem $DrivePath -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        $size = Get-FolderSizeSafe $_.FullName
        @{ name = $_.Name; size_bytes = $size; modified = $_.LastWriteTime.ToString("o") }
    }
    $result.sections.directory_sizes = @($dirSizes)
}

# ─── Output ────────────────────────────────────────────────

$json = $result | ConvertTo-Json -Depth 10 -Compress

if ($OutFile) {
    # Write without BOM so Python/JS can parse cleanly
    [System.IO.File]::WriteAllText($OutFile, $json, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Inspection complete. Output written to: $OutFile"
} else {
    $json
}
