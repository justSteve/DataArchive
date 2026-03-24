# Targeted search for business app code on I:
# Search only where code/projects would actually be
$ErrorActionPreference = "Continue"
$outFile = "C:\DataArchive\search-results.txt"
"Search started: $(Get-Date)" | Out-File $outFile -Encoding ASCII

$searchPaths = @(
    'I:\Users\steve\Documents',
    'I:\Users\steve\Desktop',
    'I:\Users\steve\OneDrive',
    'I:\Users\steve\source',
    'I:\Users\steve\repos',
    'I:\Users\steve\projects',
    'I:\Users\steve\dev',
    'I:\Users\steve\code',
    'I:\Users\steve\git',
    'I:\inetpub',
    'I:\wwwroot',
    'I:\Projects',
    'I:\repos',
    'I:\dev',
    'I:\temp'
)

$patterns = @('bankwebinar', 'cuwebinar', 'ttstrain', 'webinar', 'ttstra')

# First: just list what's in the VS project dirs and OneDrive\Code
"=== Visual Studio Projects ===" | Add-Content $outFile -Encoding ASCII
foreach ($vsDir in @(
    'I:\Users\steve\Documents\Visual Studio 2013\Projects',
    'I:\Users\steve\Documents\Visual Studio 2015\Projects',
    'I:\Users\steve\Documents\Visual Studio 2017\Projects',
    'I:\Users\steve\source\repos'
)) {
    if (Test-Path $vsDir -ErrorAction SilentlyContinue) {
        "--- $vsDir ---" | Add-Content $outFile -Encoding ASCII
        Get-ChildItem $vsDir -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            "$($_.Name)`t$($_.LastWriteTime)" | Add-Content $outFile -Encoding ASCII
        }
    }
}

"=== OneDrive\Code ===" | Add-Content $outFile -Encoding ASCII
$codePath = 'I:\Users\steve\OneDrive\Code'
if (Test-Path $codePath -ErrorAction SilentlyContinue) {
    Get-ChildItem $codePath -ErrorAction SilentlyContinue | ForEach-Object {
        $type = if ($_.PSIsContainer) { "DIR" } else { "FILE" }
        "$type`t$($_.Name)`t$($_.LastWriteTime)" | Add-Content $outFile -Encoding ASCII
    }
}

"=== IIS Sites ===" | Add-Content $outFile -Encoding ASCII
if (Test-Path 'I:\inetpub' -ErrorAction SilentlyContinue) {
    Get-ChildItem 'I:\inetpub' -Recurse -Depth 2 -ErrorAction SilentlyContinue | ForEach-Object {
        $type = if ($_.PSIsContainer) { "DIR" } else { "FILE" }
        "$type`t$($_.FullName.Replace('I:\',''))`t$($_.LastWriteTime)" | Add-Content $outFile -Encoding ASCII
    }
}

"=== Pattern Search ===" | Add-Content $outFile -Encoding ASCII
foreach ($p in $patterns) {
    "--- Pattern: $p ---" | Add-Content $outFile -Encoding ASCII
    foreach ($searchPath in $searchPaths) {
        if (Test-Path $searchPath -ErrorAction SilentlyContinue) {
            Get-ChildItem $searchPath -Recurse -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match $p } |
                ForEach-Object {
                    $fc = (Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
                    "DIR`t$($_.FullName.Replace('I:\',''))`t$fc files`t$($_.LastWriteTime)" | Add-Content $outFile -Encoding ASCII
                }
            Get-ChildItem $searchPath -Recurse -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match $p } |
                ForEach-Object {
                    "FILE`t$($_.FullName.Replace('I:\',''))`t$($_.Length) bytes`t$($_.LastWriteTime)" | Add-Content $outFile -Encoding ASCII
                }
        }
    }
}

"Search complete: $(Get-Date)" | Add-Content $outFile -Encoding ASCII
