@echo off
set DST=C:\DataArchive\business-code
set LOG=C:\DataArchive\copy-log.txt

echo === Batch copy started: %DATE% %TIME% === > %LOG%

REM source\repos
for %%R in (BankWebinars BankWebinars5 TTS TTSCore TTSWebJobs CUMailer CUMailer1 CUMailerRestored Common ConfigAssignUtility MailChimp DLLs WebJobConfigs) do (
    if exist "I:\Users\steve\source\repos\%%R" (
        echo COPY: %%R ... >> %LOG%
        robocopy "I:\Users\steve\source\repos\%%R" "%DST%\%%R" /E /R:1 /W:1 /NP /NFL /NDL > nul 2>&1
        echo DONE: %%R >> %LOG%
    ) else (
        echo SKIP: %%R - not found >> %LOG%
    )
)

REM OneDrive\Code
for %%R in (TTS TTS.API TTSCoreReference TTSProjectForGitHub TTSUtilities TTSWebJobs SQL) do (
    if exist "I:\Users\steve\OneDrive\Code\%%R" (
        echo COPY: OneDrive-%%R ... >> %LOG%
        robocopy "I:\Users\steve\OneDrive\Code\%%R" "%DST%\OneDrive-%%R" /E /R:1 /W:1 /NP /NFL /NDL > nul 2>&1
        echo DONE: OneDrive-%%R >> %LOG%
    ) else (
        echo SKIP: OneDrive-%%R - not found >> %LOG%
    )
)

echo === Batch copy complete: %DATE% %TIME% === >> %LOG%
