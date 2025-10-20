/**
 * Scan Dashboard Component
 * Displays list of recent scans with details
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Typography,
  List,
  ListItem,
  ListItemText,
  ListItemButton,
  Chip,
  Box,
  Divider,
  CircularProgress,
  Alert
} from '@mui/material';
import {
  Storage as StorageIcon,
  CheckCircle as CompleteIcon,
  Error as ErrorIcon
} from '@mui/icons-material';
import axios from 'axios';

interface Scan {
  scan_id: number;
  mount_point: string;
  scan_start: string;
  scan_end?: string;
  file_count?: number;
  total_size_bytes?: number;
  status: string;
  model?: string;
  serial_number?: string;
}

interface ScanDashboardProps {
  onScanSelected?: (scanId: number) => void;
  refreshTrigger?: number;
}

export function ScanDashboard({ onScanSelected, refreshTrigger }: ScanDashboardProps) {
  const [scans, setScans] = useState<Scan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedScanId, setSelectedScanId] = useState<number | null>(null);

  const loadScans = async () => {
    try {
      setLoading(true);
      const response = await axios.get('/api/scans');
      setScans(response.data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to load scans');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadScans();
  }, [refreshTrigger]);

  const handleScanClick = (scanId: number) => {
    setSelectedScanId(scanId);
    if (onScanSelected) {
      onScanSelected(scanId);
    }
  };

  const formatBytes = (bytes: number | undefined): string => {
    if (!bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    return date.toLocaleString();
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'COMPLETE':
        return <CompleteIcon color="success" fontSize="small" />;
      case 'FAILED':
        return <ErrorIcon color="error" fontSize="small" />;
      default:
        return <StorageIcon color="primary" fontSize="small" />;
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent>
          <Box display="flex" alignItems="center" mb={2}>
            <StorageIcon sx={{ mr: 1 }} />
            <Typography variant="h6">Recent Scans</Typography>
          </Box>
          <Box display="flex" justifyContent="center" p={3}>
            <CircularProgress />
          </Box>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent>
          <Box display="flex" alignItems="center" mb={2}>
            <StorageIcon sx={{ mr: 1 }} />
            <Typography variant="h6">Recent Scans</Typography>
          </Box>
          <Alert severity="error">{error}</Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent>
        <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
          <Box display="flex" alignItems="center">
            <StorageIcon sx={{ mr: 1 }} />
            <Typography variant="h6">Recent Scans</Typography>
          </Box>
          <Chip label={`${scans.length} total`} size="small" />
        </Box>

        {scans.length === 0 ? (
          <Alert severity="info">
            No scans found. Start a new scan to get started.
          </Alert>
        ) : (
          <List>
            {scans.map((scan, index) => (
              <React.Fragment key={scan.scan_id}>
                {index > 0 && <Divider />}
                <ListItemButton
                  onClick={() => handleScanClick(scan.scan_id)}
                  selected={selectedScanId === scan.scan_id}
                >
                  <ListItemText
                    primary={
                      <Box display="flex" alignItems="center" gap={1}>
                        {getStatusIcon(scan.status)}
                        <Typography variant="body1" fontWeight="medium">
                          {scan.model || 'Unknown Drive'}
                        </Typography>
                        <Chip
                          label={scan.status}
                          size="small"
                          color={scan.status === 'COMPLETE' ? 'success' : 'default'}
                        />
                      </Box>
                    }
                    secondary={
                      <Box mt={1}>
                        <Typography variant="body2" color="text.secondary">
                          Serial: {scan.serial_number || 'Unknown'}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Path: {scan.mount_point}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Files: {scan.file_count?.toLocaleString() || 0} •
                          Size: {formatBytes(scan.total_size_bytes)}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Scanned: {formatDate(scan.scan_start)}
                        </Typography>
                      </Box>
                    }
                  />
                </ListItemButton>
              </React.Fragment>
            ))}
          </List>
        )}
      </CardContent>
    </Card>
  );
}
