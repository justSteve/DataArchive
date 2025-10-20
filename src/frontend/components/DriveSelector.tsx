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
  Checkbox
} from '@mui/material';
import { FolderOpen as FolderIcon, Search as SearchIcon } from '@mui/icons-material';
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

  const handleStartScan = async () => {
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
        setSuccess(`Scan started successfully! Scan ID: ${response.data.scan_id}`);
        if (onScanStarted) {
          onScanStarted(response.data.scan_id);
        }
      } else {
        setError('Failed to start scan');
      }
    } catch (err: any) {
      setError(err.response?.data?.message || err.response?.data?.error || 'Failed to start scan');
    } finally {
      setLoading(false);
    }
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
    </Card>
  );
}
