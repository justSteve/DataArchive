/**
 * HealthReport Component
 * Displays Pass 1 health inspection results
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Chip,
  LinearProgress,
  Alert,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Divider,
  Tooltip,
  CircularProgress
} from '@mui/material';
import {
  CheckCircle as CheckIcon,
  Warning as WarningIcon,
  Error as ErrorIcon,
  Info as InfoIcon,
  Thermostat as TempIcon,
  Speed as SpeedIcon,
  Storage as StorageIcon,
  Memory as MemoryIcon
} from '@mui/icons-material';
import axios from 'axios';

interface HealthReportProps {
  sessionId: number;
}

interface HealthData {
  session_id: number;
  drive_path: string;
  drive_letter: string;
  inspection_time: string;
  overall_health: string;
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

export function HealthReportDisplay({ sessionId }: HealthReportProps) {
  const [data, setData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadHealthReport();
  }, [sessionId]);

  const loadHealthReport = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await axios.get(`/api/reports/${sessionId}/health`);
      setData(response.data);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to load health report');
    } finally {
      setLoading(false);
    }
  };

  const getHealthColor = (score: number): 'success' | 'warning' | 'error' | 'info' => {
    if (score >= 90) return 'success';
    if (score >= 70) return 'info';
    if (score >= 50) return 'warning';
    return 'error';
  };

  const getHealthIcon = (health: string) => {
    switch (health.toLowerCase()) {
      case 'excellent':
      case 'good':
        return <CheckIcon color="success" />;
      case 'fair':
        return <WarningIcon color="warning" />;
      case 'poor':
      case 'critical':
        return <ErrorIcon color="error" />;
      default:
        return <InfoIcon color="info" />;
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={3}>
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error">{error}</Alert>;
  }

  if (!data) {
    return <Alert severity="info">No health report available</Alert>;
  }

  return (
    <Box>
      {/* Health Score Summary */}
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={4}>
              <Box display="flex" alignItems="center" gap={1}>
                {getHealthIcon(data.overall_health)}
                <Typography variant="h5">
                  {data.overall_health}
                </Typography>
              </Box>
              <Typography variant="caption" color="text.secondary">
                Drive {data.drive_letter}: Health Status
              </Typography>
            </Grid>

            <Grid item xs={12} md={4}>
              <Box>
                <Box display="flex" justifyContent="space-between" mb={0.5}>
                  <Typography variant="body2">Health Score</Typography>
                  <Typography variant="body2" fontWeight="bold">
                    {data.health_score}/100
                  </Typography>
                </Box>
                <LinearProgress
                  variant="determinate"
                  value={data.health_score}
                  color={getHealthColor(data.health_score)}
                  sx={{ height: 10, borderRadius: 5 }}
                />
              </Box>
            </Grid>

            <Grid item xs={12} md={4}>
              <Typography variant="caption" color="text.secondary">
                Inspected: {new Date(data.inspection_time).toLocaleString()}
              </Typography>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Grid container spacing={2}>
        {/* ChkDsk Results */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Box display="flex" alignItems="center" gap={1} mb={2}>
                <StorageIcon />
                <Typography variant="h6">ChkDsk Results</Typography>
              </Box>

              {data.chkdsk ? (
                <Box>
                  <Box display="flex" flexWrap="wrap" gap={1} mb={2}>
                    <Chip
                      size="small"
                      icon={data.chkdsk.success ? <CheckIcon /> : <ErrorIcon />}
                      label={data.chkdsk.success ? 'Passed' : 'Failed'}
                      color={data.chkdsk.success ? 'success' : 'error'}
                    />
                    <Chip
                      size="small"
                      label={data.chkdsk.filesystem_type || 'Unknown FS'}
                      variant="outlined"
                    />
                    {data.chkdsk.execution_time && (
                      <Chip
                        size="small"
                        label={`${data.chkdsk.execution_time.toFixed(1)}s`}
                        variant="outlined"
                      />
                    )}
                  </Box>

                  <List dense>
                    <ListItem>
                      <ListItemIcon>
                        {data.chkdsk.errors_found ? <WarningIcon color="warning" /> : <CheckIcon color="success" />}
                      </ListItemIcon>
                      <ListItemText
                        primary="Filesystem Errors"
                        secondary={data.chkdsk.errors_found ? 'Errors found' : 'No errors'}
                      />
                    </ListItem>
                    <ListItem>
                      <ListItemIcon>
                        {data.chkdsk.bad_sectors > 0 ? <ErrorIcon color="error" /> : <CheckIcon color="success" />}
                      </ListItemIcon>
                      <ListItemText
                        primary="Bad Sectors"
                        secondary={data.chkdsk.bad_sectors > 0 ? `${data.chkdsk.bad_sectors} found` : 'None'}
                      />
                    </ListItem>
                  </List>
                </Box>
              ) : (
                <Alert severity="info">ChkDsk results not available</Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* SMART Data */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Box display="flex" alignItems="center" gap={1} mb={2}>
                <MemoryIcon />
                <Typography variant="h6">SMART Data</Typography>
              </Box>

              {data.smart?.available ? (
                <Box>
                  <Box display="flex" flexWrap="wrap" gap={1} mb={2}>
                    <Chip
                      size="small"
                      icon={data.smart.health_status?.toLowerCase() === 'healthy' ? <CheckIcon /> : <WarningIcon />}
                      label={data.smart.health_status || 'Unknown'}
                      color={data.smart.health_status?.toLowerCase() === 'healthy' ? 'success' : 'warning'}
                    />
                  </Box>

                  <Grid container spacing={1}>
                    {data.smart.temperature !== undefined && (
                      <Grid item xs={6}>
                        <Tooltip title="Drive Temperature">
                          <Box display="flex" alignItems="center" gap={0.5}>
                            <TempIcon fontSize="small" color={data.smart.temperature > 55 ? 'error' : 'success'} />
                            <Typography variant="body2">
                              {data.smart.temperature}C
                            </Typography>
                          </Box>
                        </Tooltip>
                      </Grid>
                    )}

                    {data.smart.power_on_hours !== undefined && (
                      <Grid item xs={6}>
                        <Tooltip title="Power On Hours">
                          <Box display="flex" alignItems="center" gap={0.5}>
                            <SpeedIcon fontSize="small" />
                            <Typography variant="body2">
                              {data.smart.power_on_hours.toLocaleString()} hrs
                            </Typography>
                          </Box>
                        </Tooltip>
                      </Grid>
                    )}

                    {data.smart.reallocated_sectors !== undefined && data.smart.reallocated_sectors > 0 && (
                      <Grid item xs={12}>
                        <Alert severity="warning" sx={{ mt: 1 }}>
                          Reallocated sectors: {data.smart.reallocated_sectors}
                        </Alert>
                      </Grid>
                    )}
                  </Grid>
                </Box>
              ) : (
                <Alert severity="info">
                  SMART data not available (drive may be USB or virtual)
                </Alert>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Warnings */}
        {data.warnings && data.warnings.length > 0 && (
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center" gap={1} mb={1}>
                  <WarningIcon color="warning" />
                  <Typography variant="h6">Warnings ({data.warnings.length})</Typography>
                </Box>
                <List dense>
                  {data.warnings.map((warning, index) => (
                    <ListItem key={index}>
                      <ListItemIcon>
                        <WarningIcon color="warning" fontSize="small" />
                      </ListItemIcon>
                      <ListItemText primary={warning} />
                    </ListItem>
                  ))}
                </List>
              </CardContent>
            </Card>
          </Grid>
        )}

        {/* Errors */}
        {data.errors && data.errors.length > 0 && (
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center" gap={1} mb={1}>
                  <ErrorIcon color="error" />
                  <Typography variant="h6">Errors ({data.errors.length})</Typography>
                </Box>
                <List dense>
                  {data.errors.map((err, index) => (
                    <ListItem key={index}>
                      <ListItemIcon>
                        <ErrorIcon color="error" fontSize="small" />
                      </ListItemIcon>
                      <ListItemText primary={err} />
                    </ListItem>
                  ))}
                </List>
              </CardContent>
            </Card>
          </Grid>
        )}

        {/* Recommendations */}
        {data.recommendations && data.recommendations.length > 0 && (
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Box display="flex" alignItems="center" gap={1} mb={1}>
                  <InfoIcon color="info" />
                  <Typography variant="h6">Recommendations</Typography>
                </Box>
                <List dense>
                  {data.recommendations.map((rec, index) => (
                    <ListItem key={index}>
                      <ListItemIcon>
                        <InfoIcon color="info" fontSize="small" />
                      </ListItemIcon>
                      <ListItemText primary={rec} />
                    </ListItem>
                  ))}
                </List>
              </CardContent>
            </Card>
          </Grid>
        )}
      </Grid>
    </Box>
  );
}
