# Master script: copy all business repos one by one using robocopy
$ErrorActionPreference = "Continue"
$dst = "C:\DataArchive\business-code"
$log = "C:\DataArchive\copy-log.txt"

"=== Batch copy started: $(Get-Date) ===" | Out-File $log -Encoding ASCII

$repos = @{
    "I:\Users\steve\source\repos\BankWebinars" = "$dst\BankWebinars"
    "I:\Users\steve\source\repos\BankWebinars5" = "$dst\BankWebinars5"
    "I:\Users\steve\source\repos\TTS" = "$dst\TTS"
    "I:\Users\steve\source\repos\TTSCore" = "$dst\TTSCore"
    "I:\Users\steve\source\repos\TTSWebJobs" = "$dst\TTSWebJobs"
    "I:\Users\steve\source\repos\CUMailer" = "$dst\CUMailer"
    "I:\Users\steve\source\repos\CUMailer1" = "$dst\CUMailer1"
    "I:\Users\steve\source\repos\CUMailerRestored" = "$dst\CUMailerRestored"
    "I:\Users\steve\source\repos\Common" = "$dst\Common"
    "I:\Users\steve\source\repos\ConfigAssignUtility" = "$dst\ConfigAssignUtility"
    "I:\Users\steve\source\repos\MailChimp" = "$dst\MailChimp"
    "I:\Users\steve\source\repos\DLLs" = "$dst\DLLs"
    "I:\Users\steve\source\repos\WebJobConfigs" = "$dst\WebJobConfigs"
    "I:\Users\steve\OneDrive\Code\TTS" = "$dst\OneDrive-TTS"
    "I:\Users\steve\OneDrive\Code\TTS.API" = "$dst\OneDrive-TTS.API"
    "I:\Users\steve\OneDrive\Code\TTSCoreReference" = "$dst\OneDrive-TTSCoreReference"
    "I:\Users\steve\OneDrive\Code\TTSProjectForGitHub" = "$dst\OneDrive-TTSProjectForGitHub"
    "I:\Users\steve\OneDrive\Code\TTSUtilities" = "$dst\OneDrive-TTSUtilities"
    "I:\Users\steve\OneDrive\Code\TTSWebJobs" = "$dst\OneDrive-TTSWebJobs"
    "I:\Users\steve\OneDrive\Code\SQL" = "$dst\OneDrive-SQL"
}

foreach ($src in $repos.Keys) {
    $dest = $repos[$src]
    $name = Split-Path $src -Leaf
    if (-not (Test-Path $src)) {
        "SKIP: $name - not found" | Add-Content $log -Encoding ASCII
        continue
    }
    "COPY: $name ..." | Add-Content $log -Encoding ASCII
    robocopy $src $dest /E /R:1 /W:1 /NP /NFL /NDL 2>&1 | Out-Null
    $fc = (Get-ChildItem $dest -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
    $sz = [math]::Round((Get-ChildItem $dest -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
    "DONE: $name - $fc files, $sz MB" | Add-Content $log -Encoding ASCII
}

"=== Batch copy complete: $(Get-Date) ===" | Add-Content $log -Encoding ASCII
