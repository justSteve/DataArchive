/**
 * Process Monitor Dashboard
 * Displays active processes, stalled processes, and monitoring statistics
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  Grid,
  Card,
  CardContent,
  LinearProgress,
  Chip,
  IconButton,
  Alert,
  AlertTitle,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tooltip
} from '@mui/material';
import {
  Refresh,
  Warning,
  CheckCircle,
  Error,
  HourglassEmpty,
  Speed
} from '@mui/icons-material';

interface ProcessInfo {
  processType: string;
  processId: string;
  startedAt: string;
  lastHeartbeatAt: string;
  status: 'running' | 'idle' | 'waiting' | 'stalled';
  progressPct: number;
  progressDetails?: any;
  hostInfo?: string;
}

interface MonitoringStats {
  totalProcesses: number;
  byType: Record<string, number>;
  byStatus: Record<string, number>;
  stalledProcesses: number;
}

export function ProcessMonitorDashboard() {
  const [processes, setProcesses] = useState<ProcessInfo[]>([]);
  const [stalledProcesses, setStalledProcesses] = useState<ProcessInfo[]>([]);
  const [statistics, setStatistics] = useState<MonitoringStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchData = async () => {
    try {
      setError(null);

      // Fetch active processes
      const processesRes = await fetch('/api/monitoring/processes');
      const processesData = await processesRes.json();

      // Fetch stalled processes
      const stalledRes = await fetch('/api/monitoring/stalled');
      const stalledData = await stalledRes.json();

      // Fetch statistics
      const statsRes = await fetch('/api/monitoring/statistics');
      const statsData = await statsRes.json();

      if (processesData.success) {
        setProcesses(processesData.data);
      }

      if (stalledData.success) {
        setStalledProcesses(stalledData.data);
      }

      if (statsData.success) {
        setStatistics(statsData.data);
      }

      setLoading(false);
    } catch (err: any) {
      console.error('[ProcessMonitorDashboard] Failed to fetch data:', err);
      setError(err.message || 'Failed to load monitoring data');
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();

    if (autoRefresh) {
      const interval = setInterval(fetchData, 5000); // Refresh every 5 seconds
      return () => clearInterval(interval);
    }
  }, [autoRefresh]);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running':
        return <Speed color="success" />;
      case 'idle':
        return <HourglassEmpty color="action" />;
      case 'waiting':
        return <HourglassEmpty color="warning" />;
      case 'stalled':
        return <Error color="error" />;
      default:
        return <CheckCircle color="disabled" />;
    }
  };

  const getStatusColor = (status: string): 'success' | 'warning' | 'error' | 'default' => {
    switch (status) {
      case 'running':
        return 'success';
      case 'idle':
      case 'waiting':
        return 'warning';
      case 'stalled':
        return 'error';
      default:
        return 'default';
    }
  };

  const formatDuration = (isoDate: string): string => {
    const elapsed = Date.now() - new Date(isoDate).getTime();
    const seconds = Math.floor(elapsed / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) return `${hours}h ${minutes % 60}m`;
    if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
    return `${seconds}s`;
  };

  if (loading && !processes.length) {
    return (
      <Box sx={{ p: 3, textAlign: 'center' }}>
        <LinearProgress />
        <Typography sx={{ mt: 2 }}>Loading monitoring data...</Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4">Process Monitor</Typography>
        <Box>
          <Tooltip title={autoRefresh ? 'Auto-refresh enabled' : 'Auto-refresh disabled'}>
            <Chip
              label={autoRefresh ? 'Auto-refresh ON' : 'Auto-refresh OFF'}
              color={autoRefresh ? 'success' : 'default'}
              onClick={() => setAutoRefresh(!autoRefresh)}
              sx={{ mr: 1 }}
            />
          </Tooltip>
          <Tooltip title="Refresh now">
            <IconButton onClick={fetchData}>
              <Refresh />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          <AlertTitle>Error</AlertTitle>
          {error}
        </Alert>
      )}

      {/* Statistics Cards */}
      {statistics && (
        <Grid container spacing={3} sx={{ mb: 3 }}>
          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>
                  Total Processes
                </Typography>
                <Typography variant="h3">
                  {statistics.totalProcesses}
                </Typography>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>
                  Running
                </Typography>
                <Typography variant="h3" color="success.main">
                  {statistics.byStatus['running'] || 0}
                </Typography>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <Card>
              <CardContent>
                <Typography color="text.secondary" gutterBottom>
                  Idle/Waiting
                </Typography>
                <Typography variant="h3" color="warning.main">
                  {(statistics.byStatus['idle'] || 0) + (statistics.byStatus['waiting'] || 0)}
                </Typography>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} sm={6} md={3}>
            <Card sx={{ bgcolor: statistics.stalledProcesses > 0 ? 'error.main' : undefined }}>
              <CardContent>
                <Typography
                  color={statistics.stalledProcesses > 0 ? 'error.contrastText' : 'text.secondary'}
                  gutterBottom
                >
                  Stalled
                </Typography>
                <Typography
                  variant="h3"
                  color={statistics.stalledProcesses > 0 ? 'error.contrastText' : 'error.main'}
                >
                  {statistics.stalledProcesses}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}

      {/* Stalled Processes Alert */}
      {stalledProcesses.length > 0 && (
        <Alert severity="error" icon={<Warning />} sx={{ mb: 3 }}>
          <AlertTitle>Stalled Processes Detected</AlertTitle>
          {stalledProcesses.length} process(es) have not sent a heartbeat recently and may be stuck.
        </Alert>
      )}

      {/* Active Processes Table */}
      <Paper>
        <Box sx={{ p: 2 }}>
          <Typography variant="h6">Active Processes</Typography>
        </Box>
        <TableContainer>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Type</TableCell>
                <TableCell>ID</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Progress</TableCell>
                <TableCell>Running Time</TableCell>
                <TableCell>Last Heartbeat</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {processes.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} align="center">
                    <Typography color="text.secondary" sx={{ py: 3 }}>
                      No active processes
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                processes.map((proc) => (
                  <TableRow key={`${proc.processType}-${proc.processId}`}>
                    <TableCell>
                      <Chip label={proc.processType} size="small" />
                    </TableCell>
                    <TableCell>{proc.processId}</TableCell>
                    <TableCell>
                      <Chip
                        icon={getStatusIcon(proc.status)}
                        label={proc.status}
                        color={getStatusColor(proc.status)}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <LinearProgress
                          variant="determinate"
                          value={proc.progressPct}
                          sx={{ flexGrow: 1, height: 8, borderRadius: 4 }}
                        />
                        <Typography variant="body2" color="text.secondary">
                          {proc.progressPct.toFixed(1)}%
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell>{formatDuration(proc.startedAt)}</TableCell>
                    <TableCell>
                      <Typography variant="body2" color="text.secondary">
                        {formatDuration(proc.lastHeartbeatAt)} ago
                      </Typography>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </Box>
  );
}
