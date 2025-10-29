#!/bin/bash

# DataArchive Installation Script
# This script sets up a Python virtual environment and installs all dependencies
# Similar to running an MSI installer in Windows

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
APP_NAME="dataarchive"

echo "========================================"
echo "DataArchive Installation"
echo "========================================"
echo ""

# Check if Python 3 is installed
echo "[1/5] Checking prerequisites..."
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed."
    echo "Please install Python 3 using: sudo apt update && sudo apt install python3 python3-pip python3-venv"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo "✓ Found $PYTHON_VERSION"

# Check if pip is available
if ! python3 -m pip --version &> /dev/null; then
    echo "ERROR: pip is not installed."
    echo "Please install pip using: sudo apt install python3-pip"
    exit 1
fi
echo "✓ pip is available"
echo ""

# Remove existing virtual environment if it exists
if [ -d "$VENV_DIR" ]; then
    echo "[2/5] Removing existing virtual environment..."
    rm -rf "$VENV_DIR"
    echo "✓ Cleaned up old installation"
else
    echo "[2/5] No previous installation found"
fi
echo ""

# Create virtual environment
echo "[3/5] Creating virtual environment..."
echo "This is like creating a project-specific runtime (similar to bin/Debug in .NET)"
python3 -m venv "$VENV_DIR"
echo "✓ Virtual environment created at: $VENV_DIR"
echo ""

# Activate virtual environment and install dependencies
echo "[4/5] Installing dependencies..."
echo "This is like restoring NuGet packages"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip > /dev/null 2>&1
pip install -r "$SCRIPT_DIR/requirements.txt"
deactivate
echo "✓ All dependencies installed"
echo ""

# Create launcher script
echo "[5/5] Creating launcher script..."
LAUNCHER="$SCRIPT_DIR/$APP_NAME"
cat > "$LAUNCHER" << 'EOF'
#!/bin/bash
# DataArchive Launcher
# This script activates the virtual environment and runs the application

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Run the application with all arguments passed through
python3 "$SCRIPT_DIR/scan_drive.py" "$@"

# Deactivate when done
deactivate
EOF

chmod +x "$LAUNCHER"
echo "✓ Launcher created: $LAUNCHER"
echo ""

echo "========================================"
echo "Installation Complete!"
echo "========================================"
echo ""
echo "Usage:"
echo "  ./$APP_NAME /mnt/e              # Scan E: drive"
echo "  ./$APP_NAME /mnt/c/Users        # Scan a specific folder"
echo ""
echo "The launcher script handles all the Python environment setup automatically."
echo "You don't need to worry about activating virtual environments."
echo ""
echo "To uninstall, run: ./uninstall.sh"
echo ""
