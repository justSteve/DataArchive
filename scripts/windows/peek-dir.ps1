# Quick directory listing with elevation support
# Usage: powershell.exe -ExecutionPolicy Bypass -File peek-dir.ps1 -Path "F:\MYDESK" -OutFile "C:\Temp\peek.json"
param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$false)][string]$OutFile
)

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    $tempOut = Join-Path $env:TEMP "da-peek.json"
    $scriptPath = $MyInvocation.MyCommand.Path
    Start-Process powershell.exe -Verb RunAs -ArgumentList "-ExecutionPolicy Bypass -File `"$scriptPath`" -Path `"$Path`" -OutFile `"$tempOut`"" -Wait
    if (Test-Path $tempOut) {
        if ($OutFile) { Copy-Item $tempOut $OutFile -Force }
        else { Get-Content $tempOut -Raw }
        Remove-Item $tempOut -Force
    }
    exit
}

$items = Get-ChildItem $Path -ErrorAction SilentlyContinue | ForEach-Object {
    $size = $null
    if (-not $_.PSIsContainer) { $size = $_.Length }
    else {
        try {
            $size = (Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        } catch { $size = -1 }
    }
    @{
        name = $_.Name
        is_dir = $_.PSIsContainer
        size_bytes = $size
        modified = $_.LastWriteTime.ToString("o")
        created = $_.CreationTime.ToString("o")
    }
}

$json = @($items) | ConvertTo-Json -Depth 5
if ($OutFile) {
    [System.IO.File]::WriteAllText($OutFile, $json, [System.Text.UTF8Encoding]::new($false))
} else {
    $json
}
