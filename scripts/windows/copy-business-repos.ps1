# Copy business-related repos from I:\source\repos to C:\DataArchive\business-code
$ErrorActionPreference = "Continue"
$src = "I:\Users\steve\source\repos"
$dst = "C:\DataArchive\business-code"
$log = "C:\DataArchive\copy-log.txt"

if (-not (Test-Path $dst)) { New-Item -ItemType Directory $dst | Out-Null }
"Copy started: $(Get-Date)" | Out-File $log -Encoding ASCII

$repos = @(
    'BankWebinars',
    'BankWebinars5',
    'TTS',
    'TTSCore',
    'TTSWebJobs',
    'CUMailer',
    'CUMailer1',
    'CUMailerRestored',
    'Common',
    'ConfigAssignUtility',
    'MailChimp',
    'DLLs',
    'WebJobConfigs'
)

foreach ($repo in $repos) {
    $repoPath = Join-Path $src $repo
    if (Test-Path $repoPath -ErrorAction SilentlyContinue) {
        $destPath = Join-Path $dst $repo
        "Copying: $repo ..." | Add-Content $log -Encoding ASCII
        try {
            Copy-Item $repoPath $destPath -Recurse -Force -ErrorAction Continue
            $fc = (Get-ChildItem $destPath -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
            $sz = (Get-ChildItem $destPath -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
            "OK: $repo - $fc files, $([math]::Round($sz/1MB,1)) MB" | Add-Content $log -Encoding ASCII
        } catch {
            "FAIL: $repo - $_" | Add-Content $log -Encoding ASCII
        }
    } else {
        "SKIP: $repo - not found" | Add-Content $log -Encoding ASCII
    }
}

# Also grab OneDrive\Code TTS-related dirs
$onedrive = "I:\Users\steve\OneDrive\Code"
$odRepos = @('TTS', 'TTS.API', 'TTSCoreReference', 'TTSProjectForGitHub', 'TTSUtilities', 'TTSWebJobs', 'SQL')
foreach ($repo in $odRepos) {
    $repoPath = Join-Path $onedrive $repo
    if (Test-Path $repoPath -ErrorAction SilentlyContinue) {
        $destPath = Join-Path $dst "OneDrive-$repo"
        "Copying OneDrive: $repo ..." | Add-Content $log -Encoding ASCII
        try {
            Copy-Item $repoPath $destPath -Recurse -Force -ErrorAction Continue
            $fc = (Get-ChildItem $destPath -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
            "OK: OneDrive-$repo - $fc files" | Add-Content $log -Encoding ASCII
        } catch {
            "FAIL: OneDrive-$repo - $_" | Add-Content $log -Encoding ASCII
        }
    }
}

"Copy complete: $(Get-Date)" | Add-Content $log -Encoding ASCII
