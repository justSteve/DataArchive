# Search a drive for files/folders matching patterns
# Usage: powershell.exe -ExecutionPolicy Bypass -File search-files.ps1 -DriveLetter I -Patterns "bankwebinars,cuwebinars,ttstrain" -OutFile "path"
param(
    [Parameter(Mandatory=$true)][string]$DriveLetter,
    [Parameter(Mandatory=$true)][string]$Patterns,  # comma-separated
    [Parameter(Mandatory=$false)][string]$OutFile
)

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    $tempDir = Join-Path $env:TEMP "DataArchive"
    if (-not (Test-Path $tempDir)) { New-Item -ItemType Directory $tempDir | Out-Null }
    $tempScript = Join-Path $tempDir "search-files.ps1"
    $tempOut = Join-Path $tempDir "search-$DriveLetter.json"
    Copy-Item $MyInvocation.MyCommand.Path $tempScript -Force
    $argString = "-ExecutionPolicy Bypass -File `"$tempScript`" -DriveLetter $DriveLetter -Patterns `"$Patterns`" -OutFile `"$tempOut`""
    Start-Process powershell.exe -Verb RunAs -ArgumentList $argString -Wait
    if (Test-Path $tempOut) {
        if ($OutFile) { Copy-Item $tempOut $OutFile -Force; Write-Host "Results: $OutFile" }
        else { Get-Content $tempOut -Raw }
        Remove-Item $tempOut -Force
    } else { Write-Host "ERROR: No output produced" -ForegroundColor Red }
    exit
}

$DriveLetter = $DriveLetter.TrimEnd(':')
$DrivePath = "${DriveLetter}:\"
$patternList = $Patterns -split ','

$results = @{
    drive = $DriveLetter
    searched_at = (Get-Date -Format o)
    patterns = $patternList
    matches = @()
}

foreach ($pattern in $patternList) {
    $pattern = $pattern.Trim()
    Write-Host "Searching for: $pattern ..." -ForegroundColor Yellow

    # Search directory names
    Get-ChildItem $DrivePath -Recurse -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match $pattern } |
        ForEach-Object {
            $files = Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue
            $fileCount = ($files | Measure-Object).Count
            $totalSize = ($files | Measure-Object -Property Length -Sum).Sum
            $results.matches += @{
                pattern = $pattern
                type = "directory"
                path = $_.FullName.Replace($DrivePath, '')
                name = $_.Name
                modified = $_.LastWriteTime.ToString("o")
                created = $_.CreationTime.ToString("o")
                file_count = $fileCount
                total_size = $totalSize
            }
        }

    # Search file names
    Get-ChildItem $DrivePath -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match $pattern } |
        ForEach-Object {
            $results.matches += @{
                pattern = $pattern
                type = "file"
                path = $_.FullName.Replace($DrivePath, '')
                name = $_.Name
                modified = $_.LastWriteTime.ToString("o")
                size = $_.Length
            }
        }
}

$json = $results | ConvertTo-Json -Depth 10 -Compress
if ($OutFile) {
    [System.IO.File]::WriteAllText($OutFile, $json, [System.Text.UTF8Encoding]::new($false))
} else { $json }
