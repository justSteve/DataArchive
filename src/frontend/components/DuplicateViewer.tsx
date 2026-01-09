/**
 * DuplicateViewer Component
 * Displays duplicate file groups from metadata scan
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Alert,
  CircularProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  IconButton,
  Tooltip,
  Button,
  LinearProgress
} from '@mui/material';
import {
  ExpandMore as ExpandIcon,
  FileCopy as DuplicateIcon,
  Folder as FolderIcon,
  CheckCircle as PrimaryIcon,
  Delete as DeleteIcon,
  Refresh as RefreshIcon
} from '@mui/icons-material';
import axios from 'axios';

interface DuplicateViewerProps {
  sessionId: number;
}

interface DuplicateMember {
  member_id: number;
  is_primary: boolean;
  path: string;
  size_bytes: number;
  modified_date: string;
}

interface DuplicateGroup {
  group_id: number;
  hash_value: string;
  file_size: number;
  file_count: number;
  total_wasted_bytes: number;
  status: string;
  members: DuplicateMember[];
}

export function DuplicateViewer({ sessionId }: DuplicateViewerProps) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [groups, setGroups] = useState<DuplicateGroup[]>([]);

  useEffect(() => {
    loadDuplicates();
  }, [sessionId]);

  const loadDuplicates = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await axios.get(`/api/reports/${sessionId}/duplicates`);
      setGroups(response.data.groups || []);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to load duplicates');
    } finally {
      setLoading(false);
    }
  };

  const formatBytes = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatDate = (dateStr: string): string => {
    try {
      return new Date(dateStr).toLocaleDateString();
    } catch {
      return dateStr;
    }
  };

  const getFileName = (path: string): string => {
    const parts = path.split(/[/\\]/);
    return parts[parts.length - 1] || path;
  };

  const getDirectory = (path: string): string => {
    const parts = path.split(/[/\\]/);
    parts.pop();
    return parts.join('/') || '/';
  };

  const getTotalWastedSpace = (): number => {
    return groups.reduce((total, group) => total + group.total_wasted_bytes, 0);
  };

  const getTotalDuplicateFiles = (): number => {
    return groups.reduce((total, group) => total + group.file_count - 1, 0);
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

  if (groups.length === 0) {
    return (
      <Alert severity="info">
        No duplicate files found. Each file in this scan is unique.
      </Alert>
    );
  }

  const totalWasted = getTotalWastedSpace();
  const totalDuplicates = getTotalDuplicateFiles();

  return (
    <Box>
      {/* Summary Card */}
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Box display="flex" justifyContent="space-between" alignItems="center">
            <Box display="flex" alignItems="center" gap={2}>
              <DuplicateIcon color="warning" fontSize="large" />
              <Box>
                <Typography variant="h6">
                  Duplicate Files
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {groups.length} groups containing {totalDuplicates} duplicate files
                </Typography>
              </Box>
            </Box>

            <Box display="flex" alignItems="center" gap={2}>
              <Box textAlign="right">
                <Typography variant="h5" color="warning.main">
                  {formatBytes(totalWasted)}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Potentially Recoverable
                </Typography>
              </Box>

              <Tooltip title="Refresh">
                <IconButton onClick={loadDuplicates}>
                  <RefreshIcon />
                </IconButton>
              </Tooltip>
            </Box>
          </Box>

          {/* Progress indicator for wasted space */}
          <Box mt={2}>
            <Typography variant="caption" color="text.secondary">
              Space efficiency opportunity
            </Typography>
            <LinearProgress
              variant="determinate"
              value={Math.min(100, (totalWasted / (1024 * 1024 * 1024)) * 10)} // Scale: 10GB = 100%
              color="warning"
              sx={{ height: 8, borderRadius: 4, mt: 0.5 }}
            />
          </Box>
        </CardContent>
      </Card>

      {/* Duplicate Groups */}
      {groups.map((group) => (
        <Accordion key={group.group_id} sx={{ mb: 1 }}>
          <AccordionSummary expandIcon={<ExpandIcon />}>
            <Box display="flex" alignItems="center" gap={2} width="100%">
              <DuplicateIcon color="warning" />
              <Box flexGrow={1}>
                <Typography variant="body1">
                  {getFileName(group.members[0]?.path || 'Unknown')}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {group.file_count} copies | {formatBytes(group.file_size)} each
                </Typography>
              </Box>
              <Chip
                size="small"
                label={formatBytes(group.total_wasted_bytes)}
                color="warning"
                variant="outlined"
              />
              <Chip
                size="small"
                label={group.status}
                variant="outlined"
              />
            </Box>
          </AccordionSummary>
          <AccordionDetails>
            <TableContainer component={Paper} variant="outlined">
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell width={40}></TableCell>
                    <TableCell>File Path</TableCell>
                    <TableCell align="right">Size</TableCell>
                    <TableCell align="right">Modified</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {group.members.map((member, index) => (
                    <TableRow
                      key={member.member_id}
                      sx={{
                        bgcolor: member.is_primary ? 'success.50' : undefined,
                        '&:hover': { bgcolor: 'action.hover' }
                      }}
                    >
                      <TableCell>
                        {member.is_primary ? (
                          <Tooltip title="Primary copy (will be kept)">
                            <PrimaryIcon color="success" fontSize="small" />
                          </Tooltip>
                        ) : (
                          <Tooltip title="Duplicate copy">
                            <DuplicateIcon color="disabled" fontSize="small" />
                          </Tooltip>
                        )}
                      </TableCell>
                      <TableCell>
                        <Box>
                          <Typography variant="body2">
                            {getFileName(member.path)}
                          </Typography>
                          <Typography variant="caption" color="text.secondary" component="div">
                            <FolderIcon sx={{ fontSize: 12, verticalAlign: 'middle', mr: 0.5 }} />
                            {getDirectory(member.path)}
                          </Typography>
                        </Box>
                      </TableCell>
                      <TableCell align="right">
                        <Typography variant="body2">
                          {formatBytes(member.size_bytes)}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Typography variant="body2">
                          {formatDate(member.modified_date)}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            {/* Hash info */}
            <Box mt={1} display="flex" justifyContent="space-between" alignItems="center">
              <Typography variant="caption" color="text.secondary">
                Hash: {group.hash_value.substring(0, 16)}...
              </Typography>
              <Chip
                size="small"
                label={`Group #${group.group_id}`}
                variant="outlined"
              />
            </Box>
          </AccordionDetails>
        </Accordion>
      ))}

      {/* Bottom summary */}
      <Card sx={{ mt: 2 }}>
        <CardContent>
          <Box display="flex" justifyContent="space-between" alignItems="center">
            <Typography variant="body2" color="text.secondary">
              Showing {groups.length} duplicate groups
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Total recoverable: {formatBytes(totalWasted)}
            </Typography>
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
}
