/**
 * React Error Boundary Component
 * Catches and displays errors from child components
 * Provides graceful degradation and error reporting
 */

import React, { Component, ErrorInfo, ReactNode } from 'react';
import { Box, Paper, Typography, Button, Alert, AlertTitle } from '@mui/material';
import { ErrorOutline, Refresh } from '@mui/icons-material';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null
    };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    // Update state so the next render will show the fallback UI
    return {
      hasError: true,
      error
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log error details to console
    console.error('[ErrorBoundary] Component error caught:', {
      error: error.toString(),
      stack: error.stack,
      componentStack: errorInfo.componentStack
    });

    // Update state with error info for display
    this.setState({
      error,
      errorInfo
    });

    // Call optional error handler
    if (this.props.onError) {
      try {
        this.props.onError(error, errorInfo);
      } catch (handlerError) {
        console.error('[ErrorBoundary] Error in onError handler:', handlerError);
      }
    }

    // Optional: Report to backend error tracking service
    // this.reportErrorToBackend(error, errorInfo);
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null
    });
  };

  // Optional: Report errors to backend
  // private async reportErrorToBackend(error: Error, errorInfo: ErrorInfo) {
  //   try {
  //     await fetch('/api/errors', {
  //       method: 'POST',
  //       headers: { 'Content-Type': 'application/json' },
  //       body: JSON.stringify({
  //         message: error.message,
  //         stack: error.stack,
  //         componentStack: errorInfo.componentStack,
  //         timestamp: new Date().toISOString()
  //       })
  //     });
  //   } catch (reportError) {
  //     console.error('[ErrorBoundary] Failed to report error to backend:', reportError);
  //   }
  // }

  render() {
    if (this.state.hasError) {
      // If a custom fallback is provided, use it
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default fallback UI
      return (
        <Box
          sx={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            minHeight: '400px',
            p: 3
          }}
        >
          <Paper
            elevation={3}
            sx={{
              maxWidth: 800,
              width: '100%',
              p: 4
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
              <ErrorOutline color="error" sx={{ fontSize: 48, mr: 2 }} />
              <Typography variant="h4" color="error">
                Something went wrong
              </Typography>
            </Box>

            <Alert severity="error" sx={{ mb: 3 }}>
              <AlertTitle>Error Details</AlertTitle>
              <Typography variant="body2" sx={{ fontFamily: 'monospace', mb: 1 }}>
                {this.state.error?.message || 'Unknown error'}
              </Typography>
              {this.state.error?.stack && (
                <details>
                  <summary style={{ cursor: 'pointer', marginTop: '8px' }}>
                    <Typography variant="caption" component="span">
                      View stack trace
                    </Typography>
                  </summary>
                  <Box
                    component="pre"
                    sx={{
                      mt: 2,
                      p: 2,
                      backgroundColor: 'rgba(0, 0, 0, 0.05)',
                      borderRadius: 1,
                      fontSize: '0.75rem',
                      overflow: 'auto',
                      maxHeight: 300
                    }}
                  >
                    {this.state.error.stack}
                  </Box>
                </details>
              )}
            </Alert>

            <Box sx={{ display: 'flex', gap: 2 }}>
              <Button
                variant="contained"
                color="primary"
                startIcon={<Refresh />}
                onClick={this.handleReset}
              >
                Try Again
              </Button>
              <Button
                variant="outlined"
                onClick={() => window.location.reload()}
              >
                Reload Page
              </Button>
            </Box>

            {process.env.NODE_ENV === 'development' && this.state.errorInfo && (
              <Box sx={{ mt: 3 }}>
                <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                  Component Stack (Development Only)
                </Typography>
                <Box
                  component="pre"
                  sx={{
                    p: 2,
                    backgroundColor: 'rgba(0, 0, 0, 0.05)',
                    borderRadius: 1,
                    fontSize: '0.75rem',
                    overflow: 'auto',
                    maxHeight: 200
                  }}
                >
                  {this.state.errorInfo.componentStack}
                </Box>
              </Box>
            )}
          </Paper>
        </Box>
      );
    }

    return this.props.children;
  }
}
