/**
 * Scan Progress Component
 * Displays real-time progress for an active scan
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Typography,
  LinearProgress,
  Box,
  Chip
} from '@mui/material';
import {
  CheckCircle as CheckIcon,
  Error as ErrorIcon,
  HourglassEmpty as PendingIcon
} from '@mui/icons-material';
import axios from 'axios';

interface ScanProgressProps {
  scanId: number;
  onComplete?: () => void;
}

interface ScanStatus {
  scanId: number;
  status: string;
  filesProcessed: number;
  progress: number;
}

export function ScanProgress({ scanId, onComplete }: ScanProgressProps) {
  const [status, setStatus] = useState<ScanStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let interval: NodeJS.Timeout;

    const fetchStatus = async () => {
      try {
        const response = await axios.get(`/api/scans/${scanId}/status`);
        setStatus(response.data);
        setLoading(false);
        setError(null);

        // If scan is complete, stop polling and call callback
        if (response.data.status === 'COMPLETE' && onComplete) {
          clearInterval(interval);
          onComplete();
        }
      } catch (err: any) {
        setError(err.response?.data?.error || 'Failed to fetch scan status');
        setLoading(false);
      }
    };

    // Initial fetch
    fetchStatus();

    // Poll every 2 seconds
    interval = setInterval(fetchStatus, 2000);

    return () => {
      if (interval) {
        clearInterval(interval);
      }
    };
  }, [scanId, onComplete]);

  const getStatusIcon = () => {
    if (!status) return <PendingIcon />;

    switch (status.status) {
      case 'COMPLETE':
        return <CheckIcon color="success" />;
      case 'FAILED':
        return <ErrorIcon color="error" />;
      default:
        return <PendingIcon color="primary" />;
    }
  };

  const getStatusColor = () => {
    if (!status) return 'default';

    switch (status.status) {
      case 'COMPLETE':
        return 'success';
      case 'FAILED':
        return 'error';
      case 'IN_PROGRESS':
        return 'primary';
      default:
        return 'default';
    }
  };

  if (loading && !status) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Scan Progress
          </Typography>
          <LinearProgress />
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Loading scan status...
          </Typography>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom color="error">
            Error
          </Typography>
          <Typography variant="body2">{error}</Typography>
        </CardContent>
      </Card>
    );
  }

  if (!status) return null;

  return (
    <Card>
      <CardContent>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6">
            Scan Progress
          </Typography>
          <Chip
            icon={getStatusIcon()}
            label={status.status}
            color={getStatusColor() as any}
            size="small"
          />
        </Box>

        <Box mb={2}>
          <Box display="flex" justifyContent="space-between" mb={1}>
            <Typography variant="body2" color="text.secondary">
              Files Processed
            </Typography>
            <Typography variant="body2" fontWeight="bold">
              {status.filesProcessed.toLocaleString()}
            </Typography>
          </Box>

          {status.status !== 'COMPLETE' && (
            <LinearProgress
              variant={status.progress > 0 ? 'determinate' : 'indeterminate'}
              value={status.progress}
            />
          )}

          {status.status === 'COMPLETE' && (
            <LinearProgress variant="determinate" value={100} color="success" />
          )}
        </Box>

        <Typography variant="caption" color="text.secondary">
          Scan ID: {scanId}
        </Typography>
      </CardContent>
    </Card>
  );
}
