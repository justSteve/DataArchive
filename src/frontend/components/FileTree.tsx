/**
 * File Tree Component
 * Displays files from a scan with pagination
 */

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  Box,
  Chip,
  CircularProgress,
  Alert
} from '@mui/material';
import {
  InsertDriveFile as FileIcon,
  Folder as FolderIcon
} from '@mui/icons-material';
import axios from 'axios';

interface FileInfo {
  file_id: number;
  path: string;
  size_bytes: number;
  modified_date: string;
  extension: string;
  is_hidden: boolean;
}

interface FileTreeProps {
  scanId: number | null;
}

export function FileTree({ scanId }: FileTreeProps) {
  const [files, setFiles] = useState<FileInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [totalCount, setTotalCount] = useState(0);

  useEffect(() => {
    if (scanId) {
      loadFiles();
    }
  }, [scanId, page, rowsPerPage]);

  const loadFiles = async () => {
    if (!scanId) return;

    try {
      setLoading(true);
      const offset = page * rowsPerPage;
      const response = await axios.get(`/api/files/${scanId}`, {
        params: {
          limit: rowsPerPage,
          offset
        }
      });

      setFiles(response.data.files || []);
      setTotalCount(response.data.pagination?.total || 0);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to load files');
    } finally {
      setLoading(false);
    }
  };

  const handleChangePage = (event: unknown, newPage: number) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  const formatBytes = (bytes: number): string => {
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + ' ' + sizes[i];
  };

  const formatDate = (dateString: string): string => {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  };

  const getFileIcon = (path: string) => {
    if (path.endsWith('/')) {
      return <FolderIcon fontSize="small" color="primary" />;
    }
    return <FileIcon fontSize="small" color="action" />;
  };

  if (!scanId) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            File Browser
          </Typography>
          <Alert severity="info">
            Select a scan to browse its files
          </Alert>
        </CardContent>
      </Card>
    );
  }

  if (loading && files.length === 0) {
    return (
      <Card>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            File Browser
          </Typography>
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
          <Typography variant="h6" gutterBottom>
            File Browser
          </Typography>
          <Alert severity="error">{error}</Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6">
            File Browser
          </Typography>
          <Chip label={`${totalCount.toLocaleString()} files`} size="small" />
        </Box>

        {files.length === 0 ? (
          <Alert severity="info">No files found for this scan</Alert>
        ) : (
          <>
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Path</TableCell>
                    <TableCell align="right">Size</TableCell>
                    <TableCell>Extension</TableCell>
                    <TableCell>Modified</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {files.map((file) => (
                    <TableRow key={file.file_id} hover>
                      <TableCell>
                        <Box display="flex" alignItems="center" gap={1}>
                          {getFileIcon(file.path)}
                          <Typography variant="body2" noWrap>
                            {file.path}
                          </Typography>
                          {file.is_hidden && (
                            <Chip label="Hidden" size="small" variant="outlined" />
                          )}
                        </Box>
                      </TableCell>
                      <TableCell align="right">
                        <Typography variant="body2">
                          {formatBytes(file.size_bytes)}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={file.extension || 'none'}
                          size="small"
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" color="text.secondary">
                          {formatDate(file.modified_date)}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>

            <TablePagination
              rowsPerPageOptions={[10, 25, 50, 100]}
              component="div"
              count={totalCount}
              rowsPerPage={rowsPerPage}
              page={page}
              onPageChange={handleChangePage}
              onRowsPerPageChange={handleChangeRowsPerPage}
            />
          </>
        )}
      </CardContent>
    </Card>
  );
}
