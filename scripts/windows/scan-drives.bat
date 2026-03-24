@echo off
echo Scanning drives to C:\DataArchive ...
echo Started: %DATE% %TIME%

REM Scan D:
echo === Scanning D: ===
powershell.exe -ExecutionPolicy Bypass -File "C:\DataArchive\scan-to-db.ps1" -DriveLetter D
echo D: done: %DATE% %TIME%

REM Scan I:
echo === Scanning I: ===
powershell.exe -ExecutionPolicy Bypass -File "C:\DataArchive\scan-to-db.ps1" -DriveLetter I
echo I: done: %DATE% %TIME%

echo === All scans complete: %DATE% %TIME% ===
