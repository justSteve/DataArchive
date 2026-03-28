#Requires -Version 5.1
# Import hash CSV from hash-drive.ps1 into archive.db via WSL
#
# Usage:
#   & import-hashes.ps1 -DriveLetter D -Label WWYY
#   & import-hashes.ps1 -DriveLetter E -Label Tera1A
param(
    [Parameter(Mandatory=$true)][string]$DriveLetter,
    [Parameter(Mandatory=$true)][string]$Label
)

$DriveLetter = $DriveLetter.TrimEnd(':')

Write-Host "Importing hashes for ${DriveLetter}: (${Label}) into archive.db..."
wsl --cd /root/projects/DataArchive -- python3 python/import_hashes.py "$DriveLetter" --label "$Label"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Import failed"
    exit 1
}
Write-Host "Import complete."
