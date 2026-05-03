#Requires -Version 5.1
#Requires -RunAsAdministrator
# Collect SMART data for a physical disk and write JSON for health_check.py ingestion.
#
# Usage (from elevated PowerShell):
#   .\collect-smart.ps1 -DriveLetter H -DriveCode POCL
#
# Output:  Harvester\smart\<DriveCode>-smart.json
param(
    [Parameter(Mandatory=$true)]
    [string]$DriveLetter,

    [Parameter(Mandatory=$true)]
    [string]$DriveCode
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$smartDir   = Join-Path $scriptRoot "smart"
if (-not (Test-Path $smartDir)) { New-Item -ItemType Directory $smartDir -Force | Out-Null }

$outFile = Join-Path $smartDir "$DriveCode-smart.json"

# ── Resolve the physical disk backing this drive letter ──────────────
$letter = $DriveLetter.TrimEnd(":")
$partition = Get-Partition -DriveLetter $letter -ErrorAction Stop
$diskNumber = $partition.DiskNumber

Write-Host "Drive $letter`: is on physical disk #$diskNumber"

# ── Collect PhysicalDisk info ────────────────────────────────────────
$disk = Get-PhysicalDisk -DeviceNumber $diskNumber -ErrorAction Stop

$diskInfo = @{
    device_number      = $disk.DeviceNumber
    friendly_name      = $disk.FriendlyName
    model              = $disk.Model
    serial_number      = $disk.SerialNumber
    media_type         = $disk.MediaType.ToString()
    bus_type           = $disk.BusType.ToString()
    health_status      = $disk.HealthStatus.ToString()
    operational_status = $disk.OperationalStatus.ToString()
    size_bytes         = $disk.Size
    size_gb            = [math]::Round($disk.Size / 1GB, 2)
    firmware_version   = $disk.FirmwareVersion
    logical_sector     = $disk.LogicalSectorSize
    physical_sector    = $disk.PhysicalSectorSize
}

Write-Host "  Model:    $($disk.Model)"
Write-Host "  Serial:   $($disk.SerialNumber)"
Write-Host "  Media:    $($disk.MediaType)"
Write-Host "  Health:   $($disk.HealthStatus)"
Write-Host "  OpStatus: $($disk.OperationalStatus)"
Write-Host "  Size:     $($diskInfo.size_gb) GB"

# ── Collect StorageReliabilityCounter ────────────────────────────────
$reliability = @{}
try {
    $rel = Get-PhysicalDisk -DeviceNumber $diskNumber | Get-StorageReliabilityCounter -ErrorAction Stop

    $reliability = @{
        temperature_celsius    = $rel.Temperature
        wear                   = $rel.Wear
        read_errors_total      = $rel.ReadErrorsTotal
        read_errors_corrected  = $rel.ReadErrorsCorrected
        read_errors_uncorrected = $rel.ReadErrorsUncorrected
        write_errors_total     = $rel.WriteErrorsTotal
        write_errors_corrected = $rel.WriteErrorsCorrected
        write_errors_uncorrected = $rel.WriteErrorsUncorrected
        power_on_hours         = $rel.PowerOnHours
        start_stop_cycle_count = $rel.StartStopCycleCount
    }

    # StorageReliabilityCounter doesn't expose reallocated sectors directly;
    # add whatever numeric properties it does expose.
    $relProps = $rel | Get-Member -MemberType Property | Where-Object {
        $_.Definition -match '(int|uint|long|double|float|decimal)'
    }
    foreach ($prop in $relProps) {
        $key = $prop.Name
        # Normalize to snake_case
        $snakeKey = ($key -creplace '([A-Z])', '_$1').TrimStart('_').ToLower()
        if (-not $reliability.ContainsKey($snakeKey)) {
            $reliability[$snakeKey] = $rel.$key
        }
    }

    Write-Host ""
    Write-Host "  Reliability counters:"
    Write-Host "    Temperature:   $($rel.Temperature) C"
    Write-Host "    Wear:          $($rel.Wear)"
    Write-Host "    Read errors:   $($rel.ReadErrorsTotal)"
    Write-Host "    Write errors:  $($rel.WriteErrorsTotal)"
    Write-Host "    Power-on hrs:  $($rel.PowerOnHours)"
}
catch {
    Write-Host "  (StorageReliabilityCounter not available: $($_.Exception.Message))"
    $reliability = @{ error = $_.Exception.Message }
}

# ── Assemble and write JSON ──────────────────────────────────────────
$result = @{
    drive_code        = $DriveCode
    drive_letter      = $letter
    timestamp         = (Get-Date -Format "o")
    disk              = $diskInfo
    reliability       = $reliability
    health_status     = $disk.HealthStatus.ToString()
    operational_status = $disk.OperationalStatus.ToString()
}

$jsonText = $result | ConvertTo-Json -Depth 5
$jsonText | Out-File $outFile -Encoding UTF8
Write-Host ""
Write-Host "SMART data written to: $outFile"

# ── Summary ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host ("=" * 50)
Write-Host "  SMART Collection Complete — $DriveCode"
Write-Host ("=" * 50)
Write-Host ""
Write-Host "  Drive:       $letter`:"
Write-Host "  Model:       $($disk.Model)"
Write-Host "  Health:      $($disk.HealthStatus)"
Write-Host "  Output:      $outFile"
Write-Host ""
Write-Host "  Next: run health_check.py from WSL to ingest this data."
Write-Host ""
