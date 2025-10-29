# DataArchive

A file organization system that scans drives and organizes files by type and date, with duplicate detection. Designed for WSL (Windows Subsystem for Linux) environments.

## For .NET Developers

This Python application works similarly to a standard .NET console application:
- **requirements.txt** = packages.config (dependency list)
- **venv/** = bin/ folder (isolated runtime environment)
- **install.sh** = Setup.exe (handles installation)
- **dataarchive** = your .exe (the launcher)

## Prerequisites

- Python 3.6 or higher
- WSL (Windows Subsystem for Linux) with Ubuntu/Debian recommended
- Access to drives via `/mnt/c`, `/mnt/e`, etc.

To check if Python is installed:
```bash
python3 --version
```

If not installed:
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

## Installation

1. Navigate to the project directory:
```bash
cd /mnt/c/Users/steve/OneDrive/Code/DataArchive
```

2. Make the install script executable:
```bash
chmod +x install.sh
```

3. Run the installer:
```bash
./install.sh
```

The installer will:
- Check for Python and pip
- Create an isolated virtual environment (venv)
- Install all required dependencies
- Create a launcher script
- Make everything ready to use

## Usage

After installation, use the launcher script:

```bash
# Scan a drive
./dataarchive /mnt/e

# Scan a specific folder
./dataarchive /mnt/c/Users/steve/Documents

# Scan with verbose output
./dataarchive /mnt/d --verbose
```

The launcher automatically:
- Activates the virtual environment
- Runs the application
- Deactivates the environment when done

You never need to manually activate/deactivate the virtual environment.

## What It Does

1. **Validates** the drive before scanning (checks disk status, partitions, connectivity)
2. **Scans** the specified directory recursively
3. **Categorizes** files by type (images, videos, documents, etc.)
4. **Organizes** by year and month
5. **Detects** duplicates using file hashes
6. **Generates** reports in the `reports/` directory
7. **Stores** metadata in the `storage/` directory
8. **Prevents system sleep** automatically during scanning (WSL-aware)

## Output

- **Reports**: Human-readable summaries in `reports/`
  - File statistics by type
  - Timeline of files
  - Duplicate detection results
  
- **Metadata**: JSON files in `storage/` for further processing

## Uninstallation

To remove the application (preserves your data and source code):

```bash
./uninstall.sh
```

This removes:
- Virtual environment (venv/)
- Launcher script (dataarchive)

This preserves:
- Source code
- Your scan data (storage/)
- Generated reports (reports/)

## Troubleshooting

### "Permission denied" when running scripts
```bash
chmod +x install.sh uninstall.sh
```

### "python3: command not found"
Install Python 3:
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

### "ModuleNotFoundError" errors
Run the install script again:
```bash
./install.sh
```

### Cannot access Windows drives
Ensure you're using the `/mnt/` prefix:
- C: drive = `/mnt/c`
- E: drive = `/mnt/e`

### System still goes to sleep during scan
The app automatically prevents sleep in WSL, but if it's not working:
1. Check that PowerShell is accessible from WSL: `powershell.exe -Command "Write-Host 'Test'"`
2. You may need to manually disable sleep in Windows settings for very long scans
3. The sleep prevention is automatically restored when the scan completes or is interrupted

## Project Structure

```
DataArchive/
├── install.sh          # Installation script
├── uninstall.sh        # Uninstallation script
├── dataarchive         # Launcher (created by install.sh)
├── requirements.txt    # Python dependencies
├── scan_drive.py       # Main entry point
├── core/               # Core scanning logic
│   └── file_scanner.py
├── processors/         # File processors by type
│   ├── base_processor.py
│   ├── image_processor.py
│   ├── video_processor.py
│   └── document_processor.py
├── reports/            # Generated reports (created at runtime)
├── storage/            # Metadata storage (created at runtime)
└── venv/               # Virtual environment (created by install.sh)
```

## Development Notes

If you want to modify the code:

1. The virtual environment is in `venv/`
2. Activate it manually for development:
```bash
source venv/bin/activate
```

3. Make your changes

4. Test using:
```bash
python3 scan_drive.py /path/to/test
```

5. Deactivate when done:
```bash
deactivate
```

## Future Enhancements

Based on your options trading needs, this architecture can be extended with:
- Real-time price monitoring agents
- Natural language trade expression parser
- Integration with Schwab's RTD Excel data
- Custom indicator calculations
- Trade alert monitoring

The modular processor design makes it easy to add new file types or data processing logic.
