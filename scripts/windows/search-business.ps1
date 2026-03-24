# Search I: for business app code — runs as admin
# Writes results to C:\DataArchive\search-results.txt
$ErrorActionPreference = "Continue"
$outDir = "C:\DataArchive"
$outFile = "C:\DataArchive\search-results.txt"

if (-not (Test-Path $outDir)) { New-Item -ItemType Directory $outDir | Out-Null }

"Search started: $(Get-Date)" | Out-File $outFile -Encoding ASCII

$patterns = @('bankwebinar', 'cuwebinar', 'ttstrain')

foreach ($p in $patterns) {
    "--- Pattern: $p ---" | Add-Content $outFile -Encoding ASCII

    # Directory matches
    try {
        Get-ChildItem 'I:\' -Recurse -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match $p } |
            ForEach-Object {
                $files = (Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
                "DIR`t$($_.FullName)`t$files files`t$($_.LastWriteTime)" | Add-Content $outFile -Encoding ASCII
            }
    } catch {
        "ERROR searching dirs for ${p}: $_" | Add-Content $outFile -Encoding ASCII
    }

    # File matches
    try {
        Get-ChildItem 'I:\' -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match $p } |
            ForEach-Object {
                "FILE`t$($_.FullName)`t$($_.Length) bytes`t$($_.LastWriteTime)" | Add-Content $outFile -Encoding ASCII
            }
    } catch {
        "ERROR searching files for ${p}: $_" | Add-Content $outFile -Encoding ASCII
    }
}

"Search complete: $(Get-Date)" | Add-Content $outFile -Encoding ASCII
