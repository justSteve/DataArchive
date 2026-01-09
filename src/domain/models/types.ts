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

// =========================================
// V2 INSPECTION TYPES
// =========================================

export interface InspectionSession {
  session_id: number;
  drive_id: number;
  started_at: string;
  completed_at?: string;
  status: 'active' | 'completed' | 'cancelled' | 'failed';
  current_pass: number;
  beads_issue_id?: string;
  model?: string;
  serial_number?: string;
  mount_point?: string;
  passes?: InspectionPass[];
}

export interface InspectionPass {
  pass_id: number;
  session_id: number;
  pass_number: number;
  pass_name: string;
  started_at?: string;
  completed_at?: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
  report_json?: string;
  error_message?: string;
}

export interface InspectionDecision {
  decision_id: number;
  session_id: number;
  decision_type: string;
  decision_key: string;
  decision_value: string;
  description?: string;
  decided_at: string;
  decided_by: 'user' | 'claude';
}

export interface DecisionPoint {
  decision_id: string;
  category: 'duplicate' | 'os' | 'filter' | 'custom';
  title: string;
  description: string;
  options: DecisionOption[];
  default_option?: string;
  context: Record<string, any>;
  resolved: boolean;
  resolution?: string;
  resolution_notes?: string;
}

export interface DecisionOption {
  id: string;
  label: string;
  description: string;
}

export interface HealthReport {
  session_id: number;
  drive_path: string;
  drive_letter: string;
  inspection_time: string;
  overall_health: 'Excellent' | 'Good' | 'Fair' | 'Poor' | 'Critical' | 'Unknown';
  health_score: number;
  chkdsk?: {
    success: boolean;
    filesystem_type: string;
    errors_found: boolean;
    bad_sectors: number;
    execution_time: number;
  };
  smart?: {
    available: boolean;
    health_status: string;
    temperature?: number;
    power_on_hours?: number;
    reallocated_sectors?: number;
  };
  recommendations: string[];
  warnings: string[];
  errors: string[];
  summary: string;
}

export interface OSReport {
  session_id: number;
  drive_path: string;
  drive_letter: string;
  inspection_time: string;
  os_type: string;
  os_name: string;
  version?: string;
  build_number?: string;
  edition?: string;
  install_date?: string;
  boot_capable: boolean;
  detection_method: string;
  confidence: 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN';
  user_profiles: string[];
  windows_features: Record<string, boolean>;
  installed_programs_count?: number;
  recommendations: string[];
  warnings: string[];
  errors: string[];
  summary: string;
}

export interface MetadataReport {
  session_id: number;
  total_files: number;
  total_folders: number;
  total_size_bytes: number;
  files_hashed: number;
  duplicate_groups: number;
  total_duplicate_files: number;
  wasted_bytes: number;
  cross_scan_duplicates: number;
  extension_counts: Record<string, number>;
  size_distribution: Record<string, number>;
  oldest_file_date?: string;
  newest_file_date?: string;
}

export interface ReviewReport {
  session_id: number;
  drive_path: string;
  drive_model: string;
  drive_serial: string;
  health_summary: Record<string, any>;
  os_summary: Record<string, any>;
  metadata_summary: Record<string, any>;
  decision_points: DecisionPoint[];
  resolved_decisions: InspectionDecision[];
  recommendations: string[];
  warnings: string[];
  report_path?: string;
  summary: string;
}

export interface DuplicateGroup {
  group_id: number;
  hash_value: string;
  file_size: number;
  file_count: number;
  total_wasted_bytes: number;
  status: 'unresolved' | 'keep_all' | 'keep_one' | 'deleted';
  members: DuplicateMember[];
}

export interface DuplicateMember {
  member_id: number;
  is_primary: boolean;
  path: string;
  size_bytes: number;
  modified_date: string;
}
