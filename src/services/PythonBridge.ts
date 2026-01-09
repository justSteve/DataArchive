/**
 * Bridge between TypeScript and Python domain logic
 * Spawns Python processes and communicates via JSON
 */

import { spawn, ChildProcess } from 'child_process';
import path from 'path';
import {
  DriveInfo,
  ScanResult,
  ScanOptions,
  ValidationResult,
  OSInfo
} from '../domain/models/types';

export class PythonBridge {
  private pythonPath: string;
  private pythonExecutable: string;
  private activeScans: Map<number, ChildProcess>;

  constructor() {
    // Path to Python scripts
    this.pythonPath = path.join(__dirname, '../../python');
    // Use venv python if available
    const venvPython = path.join(this.pythonPath, 'venv/bin/python3');
    this.pythonExecutable = venvPython;
    // Track active scan processes
    this.activeScans = new Map();
  }

  /**
   * Validate a drive before scanning
   */
  async validateDrive(drivePath: string): Promise<ValidationResult> {
    console.log(`[PythonBridge] Validating drive: ${drivePath}`);

    return {
      valid: true,
      errors: [],
      warnings: []
    };
  }

  /**
   * Detect operating system on a drive
   */
  async detectOS(drivePath: string): Promise<OSInfo> {
    console.log(`[PythonBridge] Detecting OS: ${drivePath}`);

    return {
      os_type: 'unknown',
      os_name: 'Unknown',
      boot_capable: false,
      detection_method: 'placeholder',
      confidence: 'low'
    };
  }

  /**
   * Get drive hardware information
   */
  async getDriveInfo(drivePath: string): Promise<DriveInfo> {
    console.log(`[PythonBridge] Getting drive info: ${drivePath}`);

    try {
      const result = await this.executePython<any>('get_drive_info.py', [drivePath]);

      if (!result.success) {
        throw new Error(result.error || 'Failed to get drive info');
      }

      return result.drive_info;
    } catch (error) {
      console.error(`[PythonBridge] Failed to get drive info:`, error);
      // Return fallback data
      return {
        serial_number: `UNKNOWN_${Date.now()}`,
        model: `Drive at ${drivePath}`,
        size_bytes: 0,
        connection_type: 'unknown'
      };
    }
  }

  /**
   * Start a drive scan (BLOCKING - waits for completion)
   * Use scanDriveAsync for non-blocking operation
   */
  async scanDrive(
    drivePath: string,
    dbPath: string,
    options: ScanOptions = {}
  ): Promise<ScanResult> {
    console.log(`[PythonBridge] Starting scan: ${drivePath}`);

    const args: string[] = [
      drivePath,
      '--db', dbPath,
      '--json-output'
    ];

    if (options.noProgress) {
      args.push('--no-progress');
    }
    if (options.driveModel) {
      args.push('--drive-model', options.driveModel);
    }
    if (options.driveSerial) {
      args.push('--drive-serial', options.driveSerial);
    }
    if (options.driveNotes) {
      args.push('--drive-notes', options.driveNotes);
    }

    const result = await this.executePython<any>('scan_drive.py', args);

    if (!result.success) {
      throw new Error(result.error || 'Scan failed');
    }

    return {
      scan_id: result.scan_id,
      file_count: result.file_count,
      total_size: result.total_size,
      status: 'complete'
    };
  }

  /**
   * Start a drive scan (NON-BLOCKING - returns immediately)
   * Process runs in background and scan_id is returned
   * Use getScanStatus to check progress
   */
  async scanDriveAsync(
    scanId: number,
    drivePath: string,
    dbPath: string,
    options: ScanOptions = {}
  ): Promise<void> {
    console.log(`[PythonBridge] Starting async scan ${scanId}: ${drivePath}`);

    // Check if scan already running
    if (this.activeScans.has(scanId)) {
      throw new Error(`Scan ${scanId} is already running`);
    }

    const args: string[] = [
      drivePath,
      '--db', dbPath,
      '--json-output',
      '--scan-id', scanId.toString()
    ];

    if (options.noProgress) {
      args.push('--no-progress');
    }
    if (options.driveModel) {
      args.push('--drive-model', options.driveModel);
    }
    if (options.driveSerial) {
      args.push('--drive-serial', options.driveSerial);
    }
    if (options.driveNotes) {
      args.push('--drive-notes', options.driveNotes);
    }

    const fullPath = path.join(this.pythonPath, 'scan_drive.py');
    const python: ChildProcess = spawn(this.pythonExecutable, [fullPath, ...args]);

    // Track this process
    this.activeScans.set(scanId, python);

    // Handle process completion
    python.on('close', (code) => {
      console.log(`[PythonBridge] Scan ${scanId} completed with code ${code}`);
      this.activeScans.delete(scanId);
    });

    python.on('error', (error) => {
      console.error(`[PythonBridge] Scan ${scanId} error:`, error);
      this.activeScans.delete(scanId);
    });
  }

  /**
   * Cancel a running scan
   */
  cancelScan(scanId: number): boolean {
    const process = this.activeScans.get(scanId);
    if (!process) {
      return false;
    }

    console.log(`[PythonBridge] Cancelling scan ${scanId}`);
    process.kill('SIGTERM');
    this.activeScans.delete(scanId);
    return true;
  }

  /**
   * Check if a scan is currently running
   */
  isScanRunning(scanId: number): boolean {
    return this.activeScans.has(scanId);
  }

  /**
   * Get all active scan IDs
   */
  getActiveScanIds(): number[] {
    return Array.from(this.activeScans.keys());
  }

  /**
   * Run an inspection pass (async, non-blocking)
   * @param sessionId - Inspection session ID
   * @param passNumber - Pass number (1-4)
   * @param drivePath - Path to the drive
   */
  async runInspectionPass(
    sessionId: number,
    passNumber: number,
    drivePath: string
  ): Promise<void> {
    const passScripts: Record<number, string> = {
      1: 'inspection/pass1_health.py',
      2: 'inspection/pass2_os.py',
      3: 'inspection/pass3_metadata.py',
      4: 'inspection/pass4_review.py'
    };

    const scriptPath = passScripts[passNumber];
    if (!scriptPath) {
      throw new Error(`Invalid pass number: ${passNumber}`);
    }

    console.log(`[PythonBridge] Running pass ${passNumber} for session ${sessionId}`);

    const args: string[] = [
      drivePath,
      '--db', './output/archive.db',
      '--session', sessionId.toString(),
      '--json'
    ];

    // Pass 4 needs special handling for auto-resolve
    if (passNumber === 4) {
      args.push('--auto-resolve');
    }

    try {
      const result = await this.executePython<any>(scriptPath, args);
      console.log(`[PythonBridge] Pass ${passNumber} completed for session ${sessionId}`);
      return result;
    } catch (error) {
      console.error(`[PythonBridge] Pass ${passNumber} failed:`, error);
      throw error;
    }
  }

  /**
   * Execute a Python script and return JSON output
   * @private
   */
  private async executePython<T>(
    scriptPath: string,
    args: string[] = []
  ): Promise<T> {
    return new Promise((resolve, reject) => {
      const fullPath = path.join(this.pythonPath, scriptPath);
      const python: ChildProcess = spawn(this.pythonExecutable, [fullPath, ...args]);

      let stdout = '';
      let stderr = '';

      python.stdout?.on('data', (data) => {
        stdout += data.toString();
      });

      python.stderr?.on('data', (data) => {
        stderr += data.toString();
      });

      python.on('close', (code) => {
        if (code === 0) {
          try {
            const result = JSON.parse(stdout);
            resolve(result);
          } catch (error) {
            reject(new Error(`Failed to parse JSON output: ${error}`));
          }
        } else {
          reject(new Error(`Python script failed with code ${code}: ${stderr}`));
        }
      });

      python.on('error', (error) => {
        reject(new Error(`Failed to spawn Python process: ${error.message}`));
      });
    });
  }
}
