# Windows Index Metadata Extraction Setup and Runner
# Run this script from Windows PowerShell (not WSL)

Write-Host "Windows Index Metadata Extraction Tools" -ForegroundColor Green
Write-Host "=======================================" -ForegroundColor Green

# Check if running on Windows
if ($env:OS -ne "Windows_NT") {
    Write-Host "ERROR: This script must be run on Windows, not WSL" -ForegroundColor Red
    Write-Host "Please run from Windows PowerShell" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if Python is available
try {
    $pythonVersion = python --version 2>$null
    Write-Host "Found Python: $pythonVersion" -ForegroundColor Green
}
catch {
    Write-Host "ERROR: Python not found in PATH" -ForegroundColor Red
    Write-Host "Please install Python and ensure it's in your PATH" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Install required package
Write-Host "`nInstalling required packages..." -ForegroundColor Yellow
try {
    pip install pywin32
    Write-Host "pywin32 installed successfully" -ForegroundColor Green
}
catch {
    Write-Host "ERROR: Failed to install pywin32" -ForegroundColor Red
    Write-Host "Error: $_" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Verify installation
Write-Host "`nVerifying installation..." -ForegroundColor Yellow
try {
    python -c "import win32com.client; print('Windows COM interface available')"
    Write-Host "Installation verified successfully!" -ForegroundColor Green
}
catch {
    Write-Host "ERROR: Cannot import win32com.client" -ForegroundColor Red
    Write-Host "Installation may have failed" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Check Windows Search service
Write-Host "`nChecking Windows Search service..." -ForegroundColor Yellow
$searchService = Get-Service -Name "WSearch" -ErrorAction SilentlyContinue
if ($searchService) {
    if ($searchService.Status -eq "Running") {
        Write-Host "Windows Search service is running" -ForegroundColor Green
    }
    else {
        Write-Host "WARNING: Windows Search service is not running" -ForegroundColor Yellow
        Write-Host "You may need to start it for indexing to work" -ForegroundColor Yellow
    }
}
else {
    Write-Host "WARNING: Windows Search service not found" -ForegroundColor Yellow
}

Write-Host "`n" -NoNewline
Write-Host "Setup Complete!" -ForegroundColor Green -BackgroundColor DarkGreen
Write-Host "`nAvailable scripts:" -ForegroundColor Cyan
Write-Host "  1. Quick directory extraction: " -NoNewline -ForegroundColor White
Write-Host "python python/quick_directory_extract.py" -ForegroundColor Yellow
Write-Host "  2. Full metadata extraction:   " -NoNewline -ForegroundColor White  
Write-Host "python python/get_windows_index_metadata.py" -ForegroundColor Yellow

Write-Host "`nNotes:" -ForegroundColor Cyan
Write-Host "  - These scripts extract metadata Windows has ALREADY indexed" -ForegroundColor White
Write-Host "  - No waiting required - retrieves existing index data immediately" -ForegroundColor White
Write-Host "  - Run these scripts from Windows PowerShell, not WSL" -ForegroundColor White

$choice = Read-Host "`nWould you like to run the quick directory extraction now? (y/n)"
if ($choice -eq "y" -or $choice -eq "Y") {
    Write-Host "`nRunning quick directory extraction..." -ForegroundColor Green
    python python/quick_directory_extract.py
}
else {
    Write-Host "`nYou can run the scripts manually when ready." -ForegroundColor Green
}

Read-Host "`nPress Enter to exit"