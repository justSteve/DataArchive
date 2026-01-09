/**
 * InspectionWizard Component
 * Main wizard for multi-pass drive inspection workflow
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Stepper,
  Step,
  StepLabel,
  StepContent,
  Button,
  Box,
  Alert,
  CircularProgress,
  TextField,
  Chip,
  LinearProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider
} from '@mui/material';
import {
  PlayArrow as PlayIcon,
  SkipNext as SkipIcon,
  CheckCircle as CheckIcon,
  Error as ErrorIcon,
  Warning as WarningIcon,
  HourglassEmpty as PendingIcon,
  Refresh as RefreshIcon,
  FolderOpen as FolderIcon
} from '@mui/icons-material';
import axios from 'axios';
import { HealthReportDisplay } from './HealthReport';
import { OSDetectionReport } from './OSDetectionReport';
import { DecisionPanel } from './DecisionPanel';

interface InspectionWizardProps {
  onInspectionComplete?: (sessionId: number) => void;
}

interface InspectionSession {
  session_id: number;
  drive_id: number;
  status: string;
  current_pass: number;
  model?: string;
  serial_number?: string;
  passes?: InspectionPass[];
}

interface InspectionPass {
  pass_id: number;
  pass_number: number;
  pass_name: string;
  status: string;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
}

const PASS_NAMES = ['Health Check', 'OS Detection', 'Metadata Capture', 'Interactive Review'];
const PASS_DESCRIPTIONS = [
  'Runs chkdsk and retrieves SMART data to assess drive health',
  'Detects operating system via registry and pattern matching',
  'Scans files, computes hashes, and identifies duplicates',
  'Compiles results and presents decision points for review'
];

export function InspectionWizard({ onInspectionComplete }: InspectionWizardProps) {
  const [drivePath, setDrivePath] = useState('/mnt/c');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Active inspection state
  const [activeInspection, setActiveInspection] = useState<InspectionSession | null>(null);
  const [passes, setPasses] = useState<InspectionPass[]>([]);
  const [pollInterval, setPollInterval] = useState<NodeJS.Timeout | null>(null);

  // Dialog state
  const [showStartDialog, setShowStartDialog] = useState(false);
  const [existingInspections, setExistingInspections] = useState<InspectionSession[]>([]);

  // Load any active inspections on mount
  useEffect(() => {
    loadActiveInspections();
    return () => {
      if (pollInterval) clearInterval(pollInterval);
    };
  }, []);

  const loadActiveInspections = async () => {
    try {
      const response = await axios.get('/api/inspections/active');
      if (response.data && response.data.length > 0) {
        setExistingInspections(response.data);
        // Auto-load the most recent active inspection
        const latest = response.data[0];
        await loadInspection(latest.session_id);
      }
    } catch (err) {
      console.error('Error loading active inspections:', err);
    }
  };

  const loadInspection = async (sessionId: number) => {
    try {
      const response = await axios.get(`/api/inspections/${sessionId}`);
      setActiveInspection(response.data);
      setPasses(response.data.passes || []);

      // Start polling if inspection is active
      if (response.data.status === 'active') {
        startPolling(sessionId);
      }
    } catch (err) {
      console.error('Error loading inspection:', err);
      setError('Failed to load inspection');
    }
  };

  const startPolling = useCallback((sessionId: number) => {
    if (pollInterval) clearInterval(pollInterval);

    const interval = setInterval(async () => {
      try {
        const response = await axios.get(`/api/inspections/${sessionId}`);
        setActiveInspection(response.data);
        setPasses(response.data.passes || []);

        // Stop polling if inspection is complete
        if (response.data.status !== 'active') {
          clearInterval(interval);
          setPollInterval(null);
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }, 3000);

    setPollInterval(interval);
  }, [pollInterval]);

  const handleStartInspection = async () => {
    if (!drivePath.trim()) {
      setError('Please enter a drive path');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await axios.post('/api/inspections/start', { drivePath });

      if (response.data.success) {
        const sessionId = response.data.session_id;
        setSuccess(`Inspection started! Session ID: ${sessionId}`);
        await loadInspection(sessionId);
        setShowStartDialog(false);
      }
    } catch (err: any) {
      setError(err.response?.data?.message || err.response?.data?.error || 'Failed to start inspection');
    } finally {
      setLoading(false);
    }
  };

  const handleStartPass = async (passNumber: number) => {
    if (!activeInspection) return;

    setLoading(true);
    setError(null);

    try {
      await axios.post(`/api/inspections/${activeInspection.session_id}/pass/${passNumber}/start`);
      setSuccess(`Pass ${passNumber} started`);
      await loadInspection(activeInspection.session_id);
    } catch (err: any) {
      setError(err.response?.data?.message || 'Failed to start pass');
    } finally {
      setLoading(false);
    }
  };

  const handleSkipPass = async (passNumber: number) => {
    if (!activeInspection) return;

    try {
      await axios.post(`/api/inspections/${activeInspection.session_id}/pass/${passNumber}/skip`, {
        reason: 'Skipped by user'
      });
      await loadInspection(activeInspection.session_id);
    } catch (err: any) {
      setError(err.response?.data?.message || 'Failed to skip pass');
    }
  };

  const handleCompleteInspection = async () => {
    if (!activeInspection) return;

    try {
      await axios.post(`/api/inspections/${activeInspection.session_id}/complete`);
      setSuccess('Inspection completed!');
      await loadInspection(activeInspection.session_id);

      if (onInspectionComplete) {
        onInspectionComplete(activeInspection.session_id);
      }
    } catch (err: any) {
      setError(err.response?.data?.message || 'Failed to complete inspection');
    }
  };

  const handleNewInspection = () => {
    setActiveInspection(null);
    setPasses([]);
    setShowStartDialog(true);
  };

  const getPassStatusIcon = (pass: InspectionPass) => {
    switch (pass.status) {
      case 'completed':
        return <CheckIcon color="success" />;
      case 'failed':
        return <ErrorIcon color="error" />;
      case 'running':
        return <CircularProgress size={20} />;
      case 'skipped':
        return <SkipIcon color="disabled" />;
      default:
        return <PendingIcon color="disabled" />;
    }
  };

  const getPassStatusChip = (pass: InspectionPass) => {
    const colorMap: Record<string, 'default' | 'primary' | 'success' | 'error' | 'warning'> = {
      pending: 'default',
      running: 'primary',
      completed: 'success',
      failed: 'error',
      skipped: 'warning'
    };
    return (
      <Chip
        size="small"
        label={pass.status.toUpperCase()}
        color={colorMap[pass.status] || 'default'}
      />
    );
  };

  const canStartPass = (passNumber: number): boolean => {
    if (!passes || passes.length === 0) return passNumber === 1;

    const currentPass = passes.find(p => p.pass_number === passNumber);
    if (!currentPass) return false;
    if (currentPass.status !== 'pending') return false;

    // Can only start if previous passes are done
    for (let i = 1; i < passNumber; i++) {
      const prevPass = passes.find(p => p.pass_number === i);
      if (!prevPass || (prevPass.status !== 'completed' && prevPass.status !== 'skipped')) {
        return false;
      }
    }
    return true;
  };

  const renderPassContent = (passNumber: number) => {
    const pass = passes.find(p => p.pass_number === passNumber);
    if (!pass) return null;

    // Show report components for completed passes
    if (pass.status === 'completed' && activeInspection) {
      switch (passNumber) {
        case 1:
          return <HealthReportDisplay sessionId={activeInspection.session_id} />;
        case 2:
          return <OSDetectionReport sessionId={activeInspection.session_id} />;
        case 4:
          return <DecisionPanel sessionId={activeInspection.session_id} />;
        default:
          return (
            <Alert severity="success">
              Pass {passNumber} completed successfully.
            </Alert>
          );
      }
    }

    // Show progress for running passes
    if (pass.status === 'running') {
      return (
        <Box>
          <LinearProgress />
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            {PASS_DESCRIPTIONS[passNumber - 1]}
          </Typography>
        </Box>
      );
    }

    // Show error for failed passes
    if (pass.status === 'failed') {
      return (
        <Alert severity="error">
          {pass.error_message || 'Pass failed with unknown error'}
        </Alert>
      );
    }

    // Show description for pending passes
    return (
      <Typography variant="body2" color="text.secondary">
        {PASS_DESCRIPTIONS[passNumber - 1]}
      </Typography>
    );
  };

  // No active inspection - show start dialog or list
  if (!activeInspection) {
    return (
      <Card>
        <CardContent>
          <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <Box display="flex" alignItems="center">
              <FolderIcon sx={{ mr: 1 }} />
              <Typography variant="h6">Drive Inspection Wizard</Typography>
            </Box>
            <Button
              variant="contained"
              startIcon={<PlayIcon />}
              onClick={() => setShowStartDialog(true)}
            >
              Start New Inspection
            </Button>
          </Box>

          {existingInspections.length > 0 && (
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Recent Inspections
              </Typography>
              <List dense>
                {existingInspections.slice(0, 5).map((insp) => (
                  <ListItem
                    key={insp.session_id}
                    button
                    onClick={() => loadInspection(insp.session_id)}
                  >
                    <ListItemIcon>
                      {insp.status === 'active' ? (
                        <CircularProgress size={20} />
                      ) : (
                        <CheckIcon color="success" />
                      )}
                    </ListItemIcon>
                    <ListItemText
                      primary={`Session ${insp.session_id}: ${insp.model || 'Unknown Drive'}`}
                      secondary={`Status: ${insp.status} | Pass: ${insp.current_pass}/4`}
                    />
                  </ListItem>
                ))}
              </List>
            </Box>
          )}

          {existingInspections.length === 0 && (
            <Alert severity="info">
              No active inspections. Click "Start New Inspection" to begin.
            </Alert>
          )}

          {/* Start Dialog */}
          <Dialog open={showStartDialog} onClose={() => setShowStartDialog(false)} maxWidth="sm" fullWidth>
            <DialogTitle>Start New Drive Inspection</DialogTitle>
            <DialogContent>
              <Box sx={{ mt: 2 }}>
                <TextField
                  fullWidth
                  label="Drive Path"
                  placeholder="/mnt/c"
                  value={drivePath}
                  onChange={(e) => setDrivePath(e.target.value)}
                  disabled={loading}
                  helperText="Enter the path to the drive you want to inspect (e.g., /mnt/d)"
                />
              </Box>

              {error && (
                <Alert severity="error" sx={{ mt: 2 }}>
                  {error}
                </Alert>
              )}

              <Box sx={{ mt: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Inspection will perform 4 passes:
                </Typography>
                <List dense>
                  {PASS_NAMES.map((name, i) => (
                    <ListItem key={i}>
                      <ListItemIcon>
                        <Chip size="small" label={i + 1} />
                      </ListItemIcon>
                      <ListItemText
                        primary={name}
                        secondary={PASS_DESCRIPTIONS[i]}
                      />
                    </ListItem>
                  ))}
                </List>
              </Box>
            </DialogContent>
            <DialogActions>
              <Button onClick={() => setShowStartDialog(false)}>Cancel</Button>
              <Button
                onClick={handleStartInspection}
                variant="contained"
                disabled={loading || !drivePath.trim()}
                startIcon={loading ? <CircularProgress size={20} /> : <PlayIcon />}
              >
                {loading ? 'Starting...' : 'Start Inspection'}
              </Button>
            </DialogActions>
          </Dialog>
        </CardContent>
      </Card>
    );
  }

  // Active inspection - show wizard stepper
  return (
    <Card>
      <CardContent>
        <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
          <Box display="flex" alignItems="center" gap={1}>
            <FolderIcon />
            <Typography variant="h6">
              Inspection #{activeInspection.session_id}
            </Typography>
            <Chip
              size="small"
              label={activeInspection.status.toUpperCase()}
              color={activeInspection.status === 'active' ? 'primary' : 'success'}
            />
          </Box>
          <Box display="flex" gap={1}>
            <Button
              size="small"
              startIcon={<RefreshIcon />}
              onClick={() => loadInspection(activeInspection.session_id)}
            >
              Refresh
            </Button>
            <Button
              size="small"
              variant="outlined"
              onClick={handleNewInspection}
            >
              New Inspection
            </Button>
          </Box>
        </Box>

        {activeInspection.model && (
          <Box mb={2}>
            <Typography variant="body2" color="text.secondary">
              Drive: {activeInspection.model}
              {activeInspection.serial_number && ` (SN: ${activeInspection.serial_number})`}
            </Typography>
          </Box>
        )}

        {error && (
          <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {success && (
          <Alert severity="success" sx={{ mb: 2 }} onClose={() => setSuccess(null)}>
            {success}
          </Alert>
        )}

        <Stepper orientation="vertical" activeStep={activeInspection.current_pass - 1}>
          {PASS_NAMES.map((name, index) => {
            const passNumber = index + 1;
            const pass = passes.find(p => p.pass_number === passNumber);

            return (
              <Step key={name} completed={pass?.status === 'completed'}>
                <StepLabel
                  icon={pass ? getPassStatusIcon(pass) : <PendingIcon />}
                  optional={
                    pass && (
                      <Box display="flex" alignItems="center" gap={1}>
                        {getPassStatusChip(pass)}
                        {pass.completed_at && (
                          <Typography variant="caption" color="text.secondary">
                            {new Date(pass.completed_at).toLocaleTimeString()}
                          </Typography>
                        )}
                      </Box>
                    )
                  }
                >
                  {name}
                </StepLabel>
                <StepContent>
                  <Box sx={{ mb: 2 }}>
                    {renderPassContent(passNumber)}
                  </Box>

                  {pass?.status === 'pending' && (
                    <Box display="flex" gap={1}>
                      <Button
                        variant="contained"
                        size="small"
                        startIcon={<PlayIcon />}
                        onClick={() => handleStartPass(passNumber)}
                        disabled={!canStartPass(passNumber) || loading}
                      >
                        Run Pass {passNumber}
                      </Button>
                      {passNumber > 1 && passNumber < 4 && (
                        <Button
                          size="small"
                          startIcon={<SkipIcon />}
                          onClick={() => handleSkipPass(passNumber)}
                          disabled={loading}
                        >
                          Skip
                        </Button>
                      )}
                    </Box>
                  )}

                  {pass?.status === 'completed' && passNumber < 4 && (
                    <Button
                      variant="contained"
                      size="small"
                      onClick={() => handleStartPass(passNumber + 1)}
                      disabled={!canStartPass(passNumber + 1) || loading}
                    >
                      Continue to Pass {passNumber + 1}
                    </Button>
                  )}
                </StepContent>
              </Step>
            );
          })}
        </Stepper>

        {/* Show complete button when all passes are done */}
        {passes.length === 4 &&
          passes.every(p => p.status === 'completed' || p.status === 'skipped') &&
          activeInspection.status === 'active' && (
            <Box mt={3}>
              <Divider sx={{ mb: 2 }} />
              <Button
                variant="contained"
                color="success"
                size="large"
                onClick={handleCompleteInspection}
                startIcon={<CheckIcon />}
              >
                Complete Inspection
              </Button>
            </Box>
          )}
      </CardContent>
    </Card>
  );
}
