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

  constructor() {
    // Path to Python scripts
    this.pythonPath = path.join(__dirname, '../../python');
    // Use venv python if available
    const venvPython = path.join(this.pythonPath, 'venv/bin/python3');
    this.pythonExecutable = venvPython;
  }

  /**
   * Validate a drive before scanning
   */
  async validateDrive(drivePath: string): Promise<ValidationResult> {
    // TODO: Implement in Phase 2
    // Will call: python/core/drive_validator.py
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
    // TODO: Implement in Phase 2
    // Will call: python/core/os_detector.py
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
    // TODO: Implement in Phase 2
    // Will call: python/core/drive_manager.py
    console.log(`[PythonBridge] Getting drive info: ${drivePath}`);

    return {
      serial_number: 'PLACEHOLDER',
      model: 'Unknown Drive',
      size_bytes: 0,
      connection_type: 'unknown'
    };
  }

  /**
   * Start a drive scan
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
