/**
 * Drive Selector Component
 * Allows user to select a drive and validate it before scanning
 */

import React, { useState } from 'react';
import {
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  Alert,
  Box,
  CircularProgress,
  FormControlLabel,
  Checkbox,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Chip
} from '@mui/material';
import { FolderOpen as FolderIcon, Search as SearchIcon, Warning as WarningIcon } from '@mui/icons-material';
import axios from 'axios';

interface DriveSelectorProps {
  onScanStarted?: (scanId: number) => void;
}

export function DriveSelector({ onScanStarted }: DriveSelectorProps) {
  const [drivePath, setDrivePath] = useState('/mnt/c');
  const [noProgress, setNoProgress] = useState(false);
  const [loading, setLoading] = useState(false);
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showDuplicateDialog, setShowDuplicateDialog] = useState(false);
  const [duplicateInfo, setDuplicateInfo] = useState<any>(null);

  const handleValidate = async () => {
    if (!drivePath.trim()) {
      setError('Please enter a drive path');
      return;
    }

    setValidating(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await axios.post('/api/drives/validate', { drivePath });

      if (response.data.valid) {
        setSuccess(`Drive "${drivePath}" is valid and ready to scan`);
      } else {
        setError(`Drive validation failed: ${response.data.errors?.join(', ') || 'Unknown error'}`);
      }
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to validate drive');
    } finally {
      setValidating(false);
    }
  };

  const handleStartScan = async (force: boolean = false) => {
    if (!drivePath.trim()) {
      setError('Please enter a drive path');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await axios.post('/api/scans/start', {
        drivePath,
        options: {
          noProgress
        }
      });

      if (response.data.success) {
        const driveModel = response.data.drive_info?.model || 'Unknown';
        setSuccess(`Scan started! Drive: ${driveModel} (Scan ID: ${response.data.scan_id})`);
        if (onScanStarted) {
          onScanStarted(response.data.scan_id);
        }
      } else {
        setError('Failed to start scan');
      }
    } catch (err: any) {
      // Check if this is a duplicate scan warning (409)
      if (err.response?.status === 409 && err.response?.data?.can_proceed && !force) {
        setDuplicateInfo(err.response.data);
        setShowDuplicateDialog(true);
      } else {
        setError(err.response?.data?.message || err.response?.data?.error || 'Failed to start scan');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleProceedWithDuplicate = () => {
    setShowDuplicateDialog(false);
    // TODO: Add force parameter to API to bypass duplicate check
    setError('Duplicate scan prevention is active. Please wait 24 hours or manually remove the check in the code.');
  };

  const handleCancelDuplicate = () => {
    setShowDuplicateDialog(false);
    setDuplicateInfo(null);
  };

  return (
    <Card>
      <CardContent>
        <Box display="flex" alignItems="center" mb={2}>
          <FolderIcon sx={{ mr: 1 }} />
          <Typography variant="h6">
            Start New Scan
          </Typography>
        </Box>

        <Box mb={2}>
          <TextField
            fullWidth
            label="Drive Path"
            placeholder="/mnt/c"
            value={drivePath}
            onChange={(e) => setDrivePath(e.target.value)}
            disabled={loading || validating}
            helperText="Enter the path to the drive you want to scan (e.g., /mnt/e)"
          />
        </Box>

        <Box mb={2}>
          <FormControlLabel
            control={
              <Checkbox
                checked={noProgress}
                onChange={(e) => setNoProgress(e.target.checked)}
                disabled={loading || validating}
              />
            }
            label="Disable progress bar (faster for large drives)"
          />
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {success && (
          <Alert severity="success" sx={{ mb: 2 }}>
            {success}
          </Alert>
        )}

        <Box display="flex" gap={2}>
          <Button
            variant="outlined"
            onClick={handleValidate}
            disabled={loading || validating || !drivePath.trim()}
            startIcon={validating ? <CircularProgress size={20} /> : <SearchIcon />}
          >
            {validating ? 'Validating...' : 'Validate Drive'}
          </Button>

          <Button
            variant="contained"
            onClick={handleStartScan}
            disabled={loading || validating || !drivePath.trim()}
            startIcon={loading ? <CircularProgress size={20} /> : <FolderIcon />}
          >
            {loading ? 'Starting...' : 'Start Scan'}
          </Button>
        </Box>

        <Box mt={2}>
          <Typography variant="caption" color="text.secondary">
            Common paths: /mnt/c (C:), /mnt/d (D:), /mnt/e (E:)
          </Typography>
        </Box>
      </CardContent>

      {/* Duplicate Scan Warning Dialog */}
      <Dialog open={showDuplicateDialog} onClose={handleCancelDuplicate}>
        <DialogTitle>
          <Box display="flex" alignItems="center" gap={1}>
            <WarningIcon color="warning" />
            Drive Recently Scanned
          </Box>
        </DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            {duplicateInfo?.warning}
          </Alert>

          {duplicateInfo?.drive_info && (
            <Box mb={2}>
              <Typography variant="subtitle2" gutterBottom>
                Drive Information:
              </Typography>
              <Box display="flex" flexDirection="column" gap={1}>
                <Chip label={`Model: ${duplicateInfo.drive_info.model}`} size="small" />
                <Chip label={`Serial: ${duplicateInfo.drive_info.serial_number}`} size="small" />
              </Box>
            </Box>
          )}

          {duplicateInfo?.last_scan && (
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Last Scan:
              </Typography>
              <Typography variant="body2">
                • Date: {new Date(duplicateInfo.last_scan.scan_start).toLocaleString()}
              </Typography>
              <Typography variant="body2">
                • Files: {duplicateInfo.last_scan.file_count?.toLocaleString() || 'Unknown'}
              </Typography>
              <Typography variant="body2">
                • Status: {duplicateInfo.last_scan.status}
              </Typography>
            </Box>
          )}

          <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
            Scanning the same drive multiple times in a short period may create duplicate data.
            Are you sure you want to proceed?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCancelDuplicate}>
            Cancel
          </Button>
          <Button onClick={handleProceedWithDuplicate} variant="contained" color="warning">
            Proceed Anyway
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
}
