/**
 * OSDetectionReport Component
 * Displays Pass 2 OS detection results
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Chip,
  Alert,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  CircularProgress,
  Divider
} from '@mui/material';
import {
  Computer as ComputerIcon,
  CheckCircle as CheckIcon,
  Warning as WarningIcon,
  Error as ErrorIcon,
  Info as InfoIcon,
  Person as PersonIcon,
  Apps as AppsIcon,
  Settings as SettingsIcon,
  Security as SecurityIcon
} from '@mui/icons-material';
import axios from 'axios';

interface OSDetectionReportProps {
  sessionId: number;
}

interface OSData {
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
  confidence: string;
  user_profiles: string[];
  windows_features: Record<string, boolean>;
  installed_programs_count?: number;
  recommendations: string[];
  warnings: string[];
  errors: string[];
  summary: string;
}

export function OSDetectionReport({ sessionId }: OSDetectionReportProps) {
  const [data, setData] = useState<OSData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadOSReport();
  }, [sessionId]);

  const loadOSReport = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await axios.get(`/api/reports/${sessionId}/os`);
      setData(response.data);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to load OS detection report');
    } finally {
      setLoading(false);
    }
  };

  const getConfidenceColor = (confidence: string): 'success' | 'warning' | 'error' | 'default' => {
    switch (confidence.toUpperCase()) {
      case 'HIGH':
        return 'success';
      case 'MEDIUM':
        return 'warning';
      case 'LOW':
        return 'error';
      default:
        return 'default';
    }
  };

  const getConfidenceIcon = (confidence: string) => {
    switch (confidence.toUpperCase()) {
      case 'HIGH':
        return <CheckIcon color="success" />;
      case 'MEDIUM':
        return <WarningIcon color="warning" />;
      case 'LOW':
        return <ErrorIcon color="error" />;
      default:
        return <InfoIcon color="info" />;
    }
  };

  const getFeatureIcon = (feature: string) => {
    if (feature.includes('security') || feature.includes('defender') || feature.includes('bitlocker')) {
      return <SecurityIcon />;
    }
    if (feature.includes('hyper') || feature.includes('wsl')) {
      return <SettingsIcon />;
    }
    if (feature.includes('visual') || feature.includes('office') || feature.includes('dotnet')) {
      return <AppsIcon />;
    }
    return <CheckIcon />;
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
    return <Alert severity="info">No OS detection report available</Alert>;
  }

  const enabledFeatures = data.windows_features
    ? Object.entries(data.windows_features)
        .filter(([_, enabled]) => enabled)
        .map(([feature]) => feature)
    : [];

  return (
    <Box>
      {/* OS Summary */}
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={6}>
              <Box display="flex" alignItems="center" gap={1}>
                <ComputerIcon fontSize="large" />
                <Box>
                  <Typography variant="h5">
                    {data.os_name}
                  </Typography>
                  {data.version && (
                    <Typography variant="body2" color="text.secondary">
                      Version {data.version}
                      {data.build_number && ` (Build ${data.build_number})`}
                    </Typography>
                  )}
                </Box>
              </Box>
            </Grid>

            <Grid item xs={12} md={6}>
              <Box display="flex" flexWrap="wrap" gap={1}>
                <Chip
                  icon={getConfidenceIcon(data.confidence)}
                  label={`${data.confidence} Confidence`}
                  color={getConfidenceColor(data.confidence)}
                  size="small"
                />
                <Chip
                  label={data.detection_method}
                  variant="outlined"
                  size="small"
                />
                {data.boot_capable && (
                  <Chip
                    icon={<CheckIcon />}
                    label="Bootable"
                    color="success"
                    size="small"
                  />
                )}
                {data.edition && (
                  <Chip
                    label={data.edition}
                    variant="outlined"
                    size="small"
                  />
                )}
              </Box>
            </Grid>
          </Grid>

          {data.install_date && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              Install Date: {data.install_date}
            </Typography>
          )}
        </CardContent>
      </Card>

      <Grid container spacing={2}>
        {/* User Profiles */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Box display="flex" alignItems="center" gap={1} mb={2}>
                <PersonIcon />
                <Typography variant="h6">
                  User Profiles ({data.user_profiles?.length || 0})
                </Typography>
              </Box>

              {data.user_profiles && data.user_profiles.length > 0 ? (
                <List dense>
                  {data.user_profiles.slice(0, 10).map((profile, index) => (
                    <ListItem key={index}>
                      <ListItemIcon>
                        <PersonIcon fontSize="small" />
                      </ListItemIcon>
                      <ListItemText primary={profile} />
                    </ListItem>
                  ))}
                  {data.user_profiles.length > 10 && (
                    <ListItem>
                      <ListItemText
                        secondary={`... and ${data.user_profiles.length - 10} more`}
                      />
                    </ListItem>
                  )}
                </List>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  No user profiles found
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Windows Features */}
        <Grid item xs={12} md={6}>
          <Card sx={{ height: '100%' }}>
            <CardContent>
              <Box display="flex" alignItems="center" gap={1} mb={2}>
                <SettingsIcon />
                <Typography variant="h6">
                  Windows Features
                </Typography>
              </Box>

              {enabledFeatures.length > 0 ? (
                <Box display="flex" flexWrap="wrap" gap={1}>
                  {enabledFeatures.map((feature, index) => {
                    // Format feature name nicely
                    const displayName = feature
                      .replace(/^has_/, '')
                      .replace(/_/g, ' ')
                      .replace(/\b\w/g, l => l.toUpperCase());

                    return (
                      <Chip
                        key={index}
                        icon={getFeatureIcon(feature)}
                        label={displayName}
                        size="small"
                        variant="outlined"
                      />
                    );
                  })}
                </Box>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  No features detected
                </Typography>
              )}

              {data.installed_programs_count !== undefined && (
                <Box mt={2}>
                  <Divider sx={{ my: 1 }} />
                  <Typography variant="body2">
                    <AppsIcon fontSize="small" sx={{ verticalAlign: 'middle', mr: 0.5 }} />
                    Approximately {data.installed_programs_count} installed programs
                  </Typography>
                </Box>
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
