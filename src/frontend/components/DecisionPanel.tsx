/**
 * DecisionPanel Component
 * Interactive decision component for Pass 4 review
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  RadioGroup,
  Radio,
  FormControlLabel,
  Button,
  Alert,
  CircularProgress,
  Chip,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Divider,
  List,
  ListItem,
  ListItemText
} from '@mui/material';
import {
  ExpandMore as ExpandIcon,
  CheckCircle as CheckIcon,
  HelpOutline as PendingIcon,
  Send as SendIcon,
  Refresh as RefreshIcon
} from '@mui/icons-material';
import axios from 'axios';

interface DecisionPanelProps {
  sessionId: number;
  onDecisionsMade?: () => void;
}

interface DecisionOption {
  id: string;
  label: string;
  description: string;
}

interface DecisionPoint {
  decision_id: string;
  category: string;
  title: string;
  description: string;
  options: DecisionOption[];
  default_option?: string;
  context: Record<string, any>;
  resolved?: boolean;
  resolution?: string;
}

interface RecordedDecision {
  decision_id: number;
  decision_type: string;
  decision_key: string;
  decision_value: string;
  description?: string;
  decided_at: string;
  decided_by: string;
}

export function DecisionPanel({ sessionId, onDecisionsMade }: DecisionPanelProps) {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [decisionPoints, setDecisionPoints] = useState<DecisionPoint[]>([]);
  const [resolvedDecisions, setResolvedDecisions] = useState<RecordedDecision[]>([]);
  const [selections, setSelections] = useState<Record<string, string>>({});

  // Summary data from review report
  const [healthSummary, setHealthSummary] = useState<Record<string, any> | null>(null);
  const [osSummary, setOsSummary] = useState<Record<string, any> | null>(null);
  const [metadataSummary, setMetadataSummary] = useState<Record<string, any> | null>(null);

  useEffect(() => {
    loadReviewReport();
  }, [sessionId]);

  const loadReviewReport = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await axios.get(`/api/reports/${sessionId}/review`);
      const data = response.data;

      setDecisionPoints(data.decision_points || []);
      setResolvedDecisions(data.resolved_decisions || []);
      setHealthSummary(data.health_summary);
      setOsSummary(data.os_summary);
      setMetadataSummary(data.metadata_summary);

      // Set default selections for unresolved decisions
      const defaults: Record<string, string> = {};
      for (const dp of data.decision_points || []) {
        if (!isResolved(dp.decision_id, data.resolved_decisions)) {
          defaults[dp.decision_id] = dp.default_option || '';
        }
      }
      setSelections(defaults);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to load review report');
    } finally {
      setLoading(false);
    }
  };

  const isResolved = (decisionId: string, resolved?: RecordedDecision[]): boolean => {
    const decisions = resolved || resolvedDecisions;
    return decisions.some(d => d.decision_key === decisionId);
  };

  const getResolvedValue = (decisionId: string): string | null => {
    const decision = resolvedDecisions.find(d => d.decision_key === decisionId);
    return decision?.decision_value || null;
  };

  const handleSelectionChange = (decisionId: string, value: string) => {
    setSelections(prev => ({
      ...prev,
      [decisionId]: value
    }));
  };

  const handleSubmitDecision = async (decisionPoint: DecisionPoint) => {
    const selectedValue = selections[decisionPoint.decision_id];
    if (!selectedValue) {
      setError('Please select an option');
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      await axios.post(`/api/decisions/${sessionId}`, {
        decisionType: decisionPoint.category,
        decisionKey: decisionPoint.decision_id,
        decisionValue: selectedValue,
        description: `${decisionPoint.title}: ${selectedValue}`,
        decidedBy: 'user'
      });

      setSuccess(`Decision recorded: ${decisionPoint.title}`);

      // Reload to update resolved status
      await loadReviewReport();

      if (onDecisionsMade) {
        onDecisionsMade();
      }
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to record decision');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmitAll = async () => {
    const unresolved = decisionPoints.filter(dp => !isResolved(dp.decision_id));
    if (unresolved.length === 0) return;

    setSubmitting(true);
    setError(null);

    try {
      const decisions = unresolved.map(dp => ({
        decisionType: dp.category,
        decisionKey: dp.decision_id,
        decisionValue: selections[dp.decision_id] || dp.default_option,
        description: `${dp.title}: ${selections[dp.decision_id] || dp.default_option}`,
        decidedBy: 'user'
      })).filter(d => d.decisionValue);

      if (decisions.length > 0) {
        await axios.post(`/api/decisions/${sessionId}/batch`, { decisions });
        setSuccess(`${decisions.length} decisions recorded`);
        await loadReviewReport();

        if (onDecisionsMade) {
          onDecisionsMade();
        }
      }
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to record decisions');
    } finally {
      setSubmitting(false);
    }
  };

  const getCategoryColor = (category: string): 'default' | 'primary' | 'secondary' | 'error' | 'warning' | 'info' | 'success' => {
    switch (category) {
      case 'duplicate':
        return 'warning';
      case 'os':
        return 'info';
      case 'filter':
        return 'secondary';
      case 'custom':
        return 'error';
      default:
        return 'default';
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" p={3}>
        <CircularProgress />
      </Box>
    );
  }

  if (error && !decisionPoints.length) {
    return <Alert severity="error">{error}</Alert>;
  }

  const unresolvedCount = decisionPoints.filter(dp => !isResolved(dp.decision_id)).length;

  return (
    <Box>
      {/* Summary Cards */}
      <Box sx={{ mb: 2, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
        {healthSummary && (
          <Chip
            label={`Health: ${healthSummary.status || 'Unknown'} (${healthSummary.score || 0}/100)`}
            color={healthSummary.score >= 70 ? 'success' : 'warning'}
            variant="outlined"
          />
        )}
        {osSummary && (
          <Chip
            label={`OS: ${osSummary.os_name || 'Unknown'}`}
            color="info"
            variant="outlined"
          />
        )}
        {metadataSummary && (
          <Chip
            label={`Files: ${(metadataSummary.total_files || 0).toLocaleString()}`}
            color="primary"
            variant="outlined"
          />
        )}
        {metadataSummary?.duplicate_groups > 0 && (
          <Chip
            label={`Duplicates: ${metadataSummary.duplicate_groups} groups`}
            color="warning"
            variant="outlined"
          />
        )}
      </Box>

      {/* Status and Actions */}
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Box display="flex" justifyContent="space-between" alignItems="center">
            <Box>
              <Typography variant="h6">
                Decision Points
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {unresolvedCount === 0
                  ? 'All decisions resolved'
                  : `${unresolvedCount} of ${decisionPoints.length} decisions pending`}
              </Typography>
            </Box>

            <Box display="flex" gap={1}>
              <Button
                startIcon={<RefreshIcon />}
                onClick={loadReviewReport}
                size="small"
              >
                Refresh
              </Button>
              {unresolvedCount > 0 && (
                <Button
                  variant="contained"
                  startIcon={submitting ? <CircularProgress size={20} /> : <SendIcon />}
                  onClick={handleSubmitAll}
                  disabled={submitting}
                >
                  Submit All ({unresolvedCount})
                </Button>
              )}
            </Box>
          </Box>
        </CardContent>
      </Card>

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

      {/* Decision Points */}
      {decisionPoints.length === 0 ? (
        <Alert severity="info">
          No decision points generated. The inspection may not have found any items requiring decisions.
        </Alert>
      ) : (
        decisionPoints.map((dp) => {
          const resolved = isResolved(dp.decision_id);
          const resolvedValue = getResolvedValue(dp.decision_id);

          return (
            <Accordion key={dp.decision_id} defaultExpanded={!resolved}>
              <AccordionSummary expandIcon={<ExpandIcon />}>
                <Box display="flex" alignItems="center" gap={1} width="100%">
                  {resolved ? (
                    <CheckIcon color="success" />
                  ) : (
                    <PendingIcon color="warning" />
                  )}
                  <Typography sx={{ flexGrow: 1 }}>
                    {dp.title}
                  </Typography>
                  <Chip
                    size="small"
                    label={dp.category}
                    color={getCategoryColor(dp.category)}
                    sx={{ mr: 1 }}
                  />
                  {resolved && (
                    <Chip
                      size="small"
                      label="Resolved"
                      color="success"
                    />
                  )}
                </Box>
              </AccordionSummary>
              <AccordionDetails>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  {dp.description}
                </Typography>

                {/* Context information */}
                {dp.context && Object.keys(dp.context).length > 0 && (
                  <Box sx={{ mb: 2, p: 1, bgcolor: 'grey.100', borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary">
                      Context:
                    </Typography>
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 0.5 }}>
                      {Object.entries(dp.context).map(([key, value]) => (
                        <Chip
                          key={key}
                          size="small"
                          label={`${key.replace(/_/g, ' ')}: ${typeof value === 'number' ? value.toLocaleString() : String(value)}`}
                          variant="outlined"
                        />
                      ))}
                    </Box>
                  </Box>
                )}

                {resolved ? (
                  <Alert severity="success">
                    Resolved: <strong>{resolvedValue}</strong>
                  </Alert>
                ) : (
                  <Box>
                    <RadioGroup
                      value={selections[dp.decision_id] || ''}
                      onChange={(e) => handleSelectionChange(dp.decision_id, e.target.value)}
                    >
                      {dp.options.map((option) => (
                        <FormControlLabel
                          key={option.id}
                          value={option.id}
                          control={<Radio />}
                          label={
                            <Box>
                              <Typography variant="body2">
                                {option.label}
                                {option.id === dp.default_option && (
                                  <Chip
                                    size="small"
                                    label="default"
                                    sx={{ ml: 1 }}
                                  />
                                )}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {option.description}
                              </Typography>
                            </Box>
                          }
                          sx={{ alignItems: 'flex-start', mb: 1 }}
                        />
                      ))}
                    </RadioGroup>

                    <Box mt={2}>
                      <Button
                        variant="outlined"
                        size="small"
                        onClick={() => handleSubmitDecision(dp)}
                        disabled={submitting || !selections[dp.decision_id]}
                        startIcon={submitting ? <CircularProgress size={16} /> : <CheckIcon />}
                      >
                        Save Decision
                      </Button>
                    </Box>
                  </Box>
                )}
              </AccordionDetails>
            </Accordion>
          );
        })
      )}

      {/* Already Resolved Decisions */}
      {resolvedDecisions.length > 0 && (
        <Card sx={{ mt: 2 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Recorded Decisions ({resolvedDecisions.length})
            </Typography>
            <List dense>
              {resolvedDecisions.map((decision) => (
                <ListItem key={decision.decision_id}>
                  <ListItemText
                    primary={`${decision.decision_key}: ${decision.decision_value}`}
                    secondary={`Decided by ${decision.decided_by} on ${new Date(decision.decided_at).toLocaleString()}`}
                  />
                </ListItem>
              ))}
            </List>
          </CardContent>
        </Card>
      )}
    </Box>
  );
}
