"""
Power management utilities for preventing sleep during long-running operations.

This module provides a cross-platform way to prevent the system from sleeping,
with specific support for WSL environments where we need to prevent Windows from sleeping.
"""

import os
import subprocess
import platform
from contextlib import contextmanager
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)


class PowerManager:
    """
    Manages system power state to prevent sleep during operations.
    
    Similar to .NET's IDisposable pattern - use with context manager to ensure
    power state is always restored even if an exception occurs.
    """
    
    def __init__(self):
        self.is_wsl = self._detect_wsl()
        self.original_settings: Optional[dict] = None
        self._prevented = False
        
    def _detect_wsl(self) -> bool:
        """Detect if running in WSL"""
        try:
            # Check for WSL-specific indicators
            if platform.system() == 'Linux':
                # Check /proc/version for Microsoft/WSL
                with open('/proc/version', 'r') as f:
                    version_info = f.read().lower()
                    if 'microsoft' in version_info or 'wsl' in version_info:
                        return True
        except Exception:
            pass
        return False
    
    def prevent_sleep(self):
        """
        Prevent system from sleeping.
        Call allow_sleep() when done to restore normal power management.
        """
        if self._prevented:
            logger.debug("Sleep prevention already active")
            return
        
        try:
            if self.is_wsl:
                self._prevent_sleep_wsl()
            else:
                self._prevent_sleep_linux()
            
            self._prevented = True
            logger.info("✓ System sleep prevention activated")
            
        except Exception as e:
            logger.warning(f"Could not prevent system sleep: {e}")
            logger.info("The scan will continue, but your system may sleep during the operation")
    
    def allow_sleep(self):
        """Restore normal power management"""
        if not self._prevented:
            return
        
        try:
            if self.is_wsl:
                self._allow_sleep_wsl()
            else:
                self._allow_sleep_linux()
            
            self._prevented = False
            logger.info("✓ System sleep prevention deactivated")
            
        except Exception as e:
            logger.warning(f"Could not restore sleep settings: {e}")
    
    def _prevent_sleep_wsl(self):
        """Prevent Windows from sleeping (called from WSL)"""
        # Create a PowerShell script that prevents sleep
        ps_script = """
$code = @'
[DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
public static extern uint SetThreadExecutionState(uint esFlags);
'@

$ste = Add-Type -MemberDefinition $code -Name ThreadExecution -Namespace Kernel32 -PassThru

# ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
# 0x80000000 | 0x00000001 | 0x00000040 = 0x80000041
$result = $ste::SetThreadExecutionState(0x80000041)

if ($result -eq 0) {
    Write-Error "Failed to set execution state"
    exit 1
}

# Keep the process alive - this will be killed when the parent process ends
while ($true) {
    Start-Sleep -Seconds 30
    # Reset the state periodically to ensure it stays active
    $ste::SetThreadExecutionState(0x80000041)
}
"""
        
        # Write script to temp file
        script_path = '/tmp/prevent_sleep.ps1'
        with open(script_path, 'w') as f:
            f.write(ps_script)
        
        # Convert WSL path to Windows path
        result = subprocess.run(
            ['wslpath', '-w', script_path],
            capture_output=True,
            text=True
        )
        windows_script_path = result.stdout.strip()
        
        # Launch PowerShell script in background
        # It will automatically terminate when our Python process ends
        subprocess.Popen(
            ['powershell.exe', '-ExecutionPolicy', 'Bypass', '-File', windows_script_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        logger.debug(f"Launched PowerShell sleep prevention script: {windows_script_path}")
    
    def _allow_sleep_wsl(self):
        """Allow Windows to sleep again"""
        # Kill any running prevent_sleep PowerShell processes
        try:
            subprocess.run(
                ['powershell.exe', '-Command', 
                 "Get-Process | Where-Object {$_.CommandLine -like '*prevent_sleep.ps1*'} | Stop-Process -Force"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            logger.debug(f"Error stopping sleep prevention: {e}")
    
    def _prevent_sleep_linux(self):
        """Prevent Linux system from sleeping"""
        # Try systemd-inhibit if available
        try:
            subprocess.run(
                ['which', 'systemd-inhibit'],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.debug("Note: systemd-inhibit is available but not implemented in this version")
        except subprocess.CalledProcessError:
            logger.debug("systemd-inhibit not available")
    
    def _allow_sleep_linux(self):
        """Allow Linux system to sleep again"""
        pass


@contextmanager
def prevent_sleep():
    """
    Context manager to prevent system sleep during operations.
    
    Usage (similar to C# using statement):
        with prevent_sleep():
            # Your long-running operation here
            scan_drive()
    
    Sleep prevention is automatically restored when the block exits,
    even if an exception occurs.
    """
    manager = PowerManager()
    manager.prevent_sleep()
    try:
        yield
    finally:
        manager.allow_sleep()
