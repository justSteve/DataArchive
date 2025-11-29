/**
 * LogViewer - Real-time server log viewer
 * Displays Express server logs in a console-like interface
 */

import React, { useState, useEffect, useRef } from 'react';
import {
  Paper,
  Typography,
  Box,
  IconButton,
  Switch,
  FormControlLabel,
  Chip
} from '@mui/material';
import {
  Clear as ClearIcon,
  PauseCircle as PauseIcon,
  PlayCircle as PlayIcon
} from '@mui/icons-material';

interface LogEntry {
  timestamp: string;
  level: 'log' | 'info' | 'warn' | 'error';
  message: string;
}

export const LogViewer: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [isPaused, setIsPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [isConnected, setIsConnected] = useState(false);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    // Connect to SSE endpoint
    const eventSource = new EventSource('/api/logs/stream');
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      console.log('Connected to log stream');
      setIsConnected(true);
    };

    eventSource.onmessage = (event) => {
      if (isPaused) return;

      try {
        const entry: LogEntry = JSON.parse(event.data);
        setLogs(prev => [...prev, entry].slice(-1000)); // Keep last 1000 logs
      } catch (error) {
        console.error('Failed to parse log entry:', error);
      }
    };

    eventSource.onerror = (error) => {
      console.error('Log stream error:', error);
      setIsConnected(false);
    };

    // Cleanup on unmount
    return () => {
      eventSource.close();
    };
  }, [isPaused]);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const handleClear = () => {
    setLogs([]);
  };

  const handleTogglePause = () => {
    setIsPaused(!isPaused);
  };

  const getLogColor = (level: LogEntry['level']) => {
    switch (level) {
      case 'error':
        return '#ff5252';
      case 'warn':
        return '#ffa726';
      case 'info':
        return '#42a5f5';
      default:
        return '#e0e0e0';
    }
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  return (
    <Paper elevation={3} sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <Box
        sx={{
          p: 2,
          borderBottom: '1px solid #e0e0e0',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          backgroundColor: '#f5f5f5'
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Typography variant="h6">Server Logs</Typography>
          <Chip
            label={isConnected ? 'Connected' : 'Disconnected'}
            color={isConnected ? 'success' : 'error'}
            size="small"
          />
          <Chip label={`${logs.length} entries`} size="small" />
        </Box>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <FormControlLabel
            control={
              <Switch
                checked={autoScroll}
                onChange={(e) => setAutoScroll(e.target.checked)}
                size="small"
              />
            }
            label="Auto-scroll"
          />
          <IconButton onClick={handleTogglePause} size="small" title={isPaused ? 'Resume' : 'Pause'}>
            {isPaused ? <PlayIcon /> : <PauseIcon />}
          </IconButton>
          <IconButton onClick={handleClear} size="small" title="Clear logs">
            <ClearIcon />
          </IconButton>
        </Box>
      </Box>

      {/* Log Container */}
      <Box
        ref={logContainerRef}
        sx={{
          flex: 1,
          overflow: 'auto',
          backgroundColor: '#1e1e1e',
          color: '#e0e0e0',
          fontFamily: 'Consolas, Monaco, "Courier New", monospace',
          fontSize: '13px',
          p: 2
        }}
      >
        {logs.length === 0 ? (
          <Typography sx={{ color: '#666', textAlign: 'center', mt: 4 }}>
            No logs yet. Waiting for server activity...
          </Typography>
        ) : (
          logs.map((log, index) => (
            <Box
              key={index}
              sx={{
                display: 'flex',
                gap: 2,
                mb: 0.5,
                '&:hover': {
                  backgroundColor: 'rgba(255, 255, 255, 0.05)'
                }
              }}
            >
              <Typography
                component="span"
                sx={{
                  color: '#888',
                  minWidth: '70px',
                  fontFamily: 'inherit'
                }}
              >
                {formatTimestamp(log.timestamp)}
              </Typography>
              <Typography
                component="span"
                sx={{
                  color: getLogColor(log.level),
                  fontWeight: 'bold',
                  minWidth: '50px',
                  textTransform: 'uppercase',
                  fontFamily: 'inherit'
                }}
              >
                {log.level}
              </Typography>
              <Typography
                component="span"
                sx={{
                  color: '#e0e0e0',
                  wordBreak: 'break-word',
                  fontFamily: 'inherit',
                  flex: 1
                }}
              >
                {log.message}
              </Typography>
            </Box>
          ))
        )}
      </Box>
    </Paper>
  );
};
