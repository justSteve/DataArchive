# Copy a single repo with robust error handling
param(
    [Parameter(Mandatory=$true)][string]$Source,
    [Parameter(Mandatory=$true)][string]$Dest
)
$ErrorActionPreference = "Continue"
$log = "C:\DataArchive\copy-log.txt"

try {
    if (-not (Test-Path $Source)) {
        "SKIP: $Source not found" | Add-Content $log -Encoding ASCII
        exit 0
    }
    $name = Split-Path $Source -Leaf
    "START: $name $(Get-Date)" | Add-Content $log -Encoding ASCII

    robocopy $Source $Dest /E /R:1 /W:1 /NP /NFL /NDL /MT:4 2>&1 | Out-Null

    $fc = (Get-ChildItem $Dest -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
    $sz = [math]::Round((Get-ChildItem $Dest -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
    "DONE: $name - $fc files, $sz MB $(Get-Date)" | Add-Content $log -Encoding ASCII
} catch {
    "FAIL: $Source - $_ $(Get-Date)" | Add-Content $log -Encoding ASCII
}
