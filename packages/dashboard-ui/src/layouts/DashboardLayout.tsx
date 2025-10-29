import React from 'react';
import { ThemeProvider, CssBaseline, Box, AppBar, Toolbar, Typography, Container } from '@mui/material';
import { darkTheme } from '../theme/darkTheme';

export interface DashboardLayoutProps {
  /**
   * Application title displayed in app bar
   */
  title: string;

  /**
   * Child components to render in the main content area
   */
  children: React.ReactNode;

  /**
   * Optional custom theme (defaults to dark theme)
   */
  theme?: typeof darkTheme;

  /**
   * Maximum width of the container
   */
  maxWidth?: 'xs' | 'sm' | 'md' | 'lg' | 'xl' | false;
}

/**
 * Main dashboard layout with app bar and container
 */
export function DashboardLayout({
  title,
  children,
  theme = darkTheme,
  maxWidth = 'xl'
}: DashboardLayoutProps) {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        <AppBar position="static">
          <Toolbar>
            <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
              {title}
            </Typography>
          </Toolbar>
        </AppBar>
        <Container maxWidth={maxWidth} sx={{ mt: 4, mb: 4, flex: 1 }}>
          {children}
        </Container>
      </Box>
    </ThemeProvider>
  );
}
