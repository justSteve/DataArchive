/**
 * Type definitions matching Python data structures
 */

export interface DriveInfo {
  serial_number: string;
  model: string;
  manufacturer?: string;
  size_bytes: number;
  filesystem?: string;
  connection_type: string;
  media_type?: string;
  bus_type?: string;
  firmware_version?: string;
}

export interface ScanOptions {
  noProgress?: boolean;
  driveModel?: string;
  driveSerial?: string;
  driveNotes?: string;
}

export interface ScanResult {
  scan_id: number;
  file_count: number;
  total_size: number;
  status: 'in_progress' | 'complete' | 'failed';
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  drive_info?: {
    accessible: boolean;
    total_bytes: number;
    free_bytes: number;
    filesystem: string;
  };
}

export interface FileInfo {
  file_id: number;
  scan_id: number;
  path: string;
  size_bytes: number;
  modified_date: string;
  created_date: string;
  accessed_date?: string;
  extension: string;
  is_hidden: boolean;
  is_system: boolean;
}

export interface OSInfo {
  os_type: string;
  os_name: string;
  version?: string;
  build_number?: string;
  edition?: string;
  install_date?: string;
  boot_capable: boolean;
  detection_method: string;
  confidence: string;
}

export interface ScanInfo {
  scan_id: number;
  drive_id: number;
  scan_start: string;
  scan_end?: string;
  mount_point: string;
  file_count?: number;
  total_size_bytes?: number;
  status: string;
  model?: string;
  serial_number?: string;
}

export interface ScanStatus {
  status: 'idle' | 'validating' | 'scanning' | 'complete' | 'failed';
  filesProcessed?: number;
  totalFiles?: number;
  progress?: number;
  currentFile?: string;
  error?: string;
}
