/**
 * Admin Panel Component
 * Database management and system utilities
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Button,
  Box,
  Alert,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Chip,
  Divider,
  List,
  ListItem,
  ListItemText
} from '@mui/material';
import {
  Delete as DeleteIcon,
  Refresh as RefreshIcon,
  Storage as StorageIcon,
  Warning as WarningIcon
} from '@mui/icons-material';
import axios from 'axios';

export const AdminPanel: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [stats, setStats] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [backups, setBackups] = useState<any[]>([]);

  useEffect(() => {
    loadStats();
    loadBackups();
  }, []);

  const loadStats = async () => {
    try {
      const response = await axios.get('/api/admin/database-stats');
      setStats(response.data);
    } catch (err) {
      console.error('Failed to load stats:', err);
    }
  };

  const loadBackups = async () => {
    try {
      const response = await axios.get('/api/admin/backups');
      setBackups(response.data.backups || []);
    } catch (err) {
      console.error('Failed to load backups:', err);
    }
  };

  const handleResetDatabase = async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await axios.post('/api/admin/reset-database', {
        confirm: true
      });

      if (response.data.success) {
        setSuccess('Database reset successfully! All data cleared and backed up.');
        setShowConfirmDialog(false);
        // Reload stats and backups
        await loadStats();
        await loadBackups();
      } else {
        setError('Failed to reset database');
      }
    } catch (err: any) {
      setError(err.response?.data?.message || 'Failed to reset database');
    } finally {
      setLoading(false);
    }
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <Box>
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box display="flex" alignItems="center" mb={2}>
            <StorageIcon sx={{ mr: 1 }} />
            <Typography variant="h6">Database Statistics</Typography>
            <Button
              size="small"
              startIcon={<RefreshIcon />}
              onClick={() => { loadStats(); loadBackups(); }}
              sx={{ ml: 'auto' }}
            >
              Refresh
            </Button>
          </Box>

          {stats && (
            <Box>
              <Box display="flex" gap={2} mb={2} flexWrap="wrap">
                <Chip
                  label={`Size: ${stats.size_mb} MB`}
                  color="primary"
                  variant="outlined"
                />
                <Chip
                  label={`Scans: ${stats.scans}`}
                  color="secondary"
                  variant="outlined"
                />
                <Chip
                  label={`Drives: ${stats.drives}`}
                  color="info"
                  variant="outlined"
                />
                <Chip
                  label={`Files: ${stats.files?.toLocaleString()}`}
                  color="success"
                  variant="outlined"
                />
              </Box>

              <Typography variant="caption" color="text.secondary">
                Database path: {stats.path}
              </Typography>
            </Box>
          )}

          {error && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {error}
            </Alert>
          )}

          {success && (
            <Alert severity="success" sx={{ mt: 2 }}>
              {success}
            </Alert>
          )}
        </CardContent>
      </Card>

      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Danger Zone
          </Typography>

          <Alert severity="warning" sx={{ mb: 2 }}>
            Resetting the database will delete all scans and data. A backup will be created automatically.
          </Alert>

          <Button
            variant="contained"
            color="error"
            startIcon={<DeleteIcon />}
            onClick={() => setShowConfirmDialog(true)}
            disabled={loading}
          >
            Reset Database
          </Button>
        </CardContent>
      </Card>

      {backups.length > 0 && (
        <Card>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Database Backups ({backups.length})
            </Typography>

            <List dense>
              {backups.slice(0, 5).map((backup, index) => (
                <React.Fragment key={backup.filename}>
                  {index > 0 && <Divider />}
                  <ListItem>
                    <ListItemText
                      primary={backup.filename}
                      secondary={
                        <>
                          {formatBytes(backup.size_bytes)} • {new Date(backup.created).toLocaleString()}
                        </>
                      }
                    />
                  </ListItem>
                </React.Fragment>
              ))}
            </List>

            {backups.length > 5 && (
              <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                ... and {backups.length - 5} more backups
              </Typography>
            )}

            <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
              Backup location: output/backups/
            </Typography>
          </CardContent>
        </Card>
      )}

      {/* Confirmation Dialog */}
      <Dialog open={showConfirmDialog} onClose={() => setShowConfirmDialog(false)}>
        <DialogTitle>
          <Box display="flex" alignItems="center" gap={1}>
            <WarningIcon color="error" />
            Confirm Database Reset
          </Box>
        </DialogTitle>
        <DialogContent>
          <Alert severity="error" sx={{ mb: 2 }}>
            This will permanently delete all scan data!
          </Alert>

          <Typography variant="body2" paragraph>
            The following will be deleted:
          </Typography>

          <Box component="ul" sx={{ pl: 2 }}>
            <li><Typography variant="body2">All {stats?.scans} scans</Typography></li>
            <li><Typography variant="body2">All {stats?.drives} drive records</Typography></li>
            <li><Typography variant="body2">All {stats?.files?.toLocaleString()} file records</Typography></li>
          </Box>

          <Typography variant="body2" sx={{ mt: 2 }}>
            A backup will be created at: <code>output/backups/archive_backup_[timestamp].db</code>
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowConfirmDialog(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleResetDatabase}
            variant="contained"
            color="error"
            disabled={loading}
            startIcon={loading ? <CircularProgress size={20} /> : <DeleteIcon />}
          >
            {loading ? 'Resetting...' : 'Yes, Reset Database'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
