#Requires -Version 5.1
# Harvest Plan — calls the Python manifest generator via WSL
#
# This is a thin Windows wrapper. The actual logic lives in
# python/harvest_plan.py in the WSL repo, which queries archive.db
# and writes the manifest to the Harvester directory.
#
# Usage:
#   & harvest-plan.ps1 -Label WWYY
#   & harvest-plan.ps1 -Label Tera1A
#   & harvest-plan.ps1 -Label Tera1A -Staging G:
param(
    [Parameter(Mandatory=$true)][string]$Label,
    [string]$Staging = "F:"
)

$configPath = "C:\myStuff\DataArchive\Harvester\configs\${Label}.json"
if (-not (Test-Path $configPath)) {
    Write-Error "Config not found: $configPath"
    exit 1
}

$wslConfigPath = $configPath.Replace('\', '/').Replace('C:', '/mnt/c')

Write-Host "Generating harvest manifest for $Label..."
Write-Host "Config: $configPath"
Write-Host ""

wsl --cd /root/projects/DataArchive -- python3 python/harvest_plan.py --config "$wslConfigPath" --staging "$Staging"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Manifest generation failed"
    exit 1
}

Write-Host ""
Write-Host "-- Next step: execute in elevated PowerShell --"
Write-Host "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass"
Write-Host "& `"C:\Users\steve\OneDrive\Tools\DataArchiver\harvest-execute.ps1`" -Manifest `"C:\myStuff\DataArchive\Harvester\manifests\harvest-${Label}.jsonl`""
