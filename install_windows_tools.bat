@echo off
echo Installing Windows Index Metadata Extraction Tools
echo ================================================

REM Check if we're running on Windows
if not "%OS%"=="Windows_NT" (
    echo This script must be run on Windows, not WSL
    echo Please run from Windows PowerShell or Command Prompt
    pause
    exit /b 1
)

REM Install required Python package
echo Installing pywin32...
pip install pywin32

REM Verify installation
echo.
echo Verifying installation...
python -c "import win32com.client; print('pywin32 installed successfully')" 2>nul
if errorlevel 1 (
    echo ERROR: pywin32 installation failed
    echo Please ensure you have Python and pip installed
    pause
    exit /b 1
)

echo.
echo Installation complete!
echo.
echo To run the extraction scripts:
echo   Quick directory structure: python python/quick_directory_extract.py
echo   Full metadata extraction:  python python/get_windows_index_metadata.py
echo.
echo Note: Make sure Windows Search is running and has indexed your E: drive
pause