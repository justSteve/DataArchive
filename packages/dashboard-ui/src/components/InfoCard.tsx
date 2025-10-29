import React from 'react';
import { Card, CardContent, Typography, Box } from '@mui/material';

export interface InfoCardProps {
  /**
   * Card title
   */
  title: string;

  /**
   * Main value to display
   */
  value: string | number;

  /**
   * Optional subtitle or description
   */
  subtitle?: string;

  /**
   * Optional icon to display
   */
  icon?: React.ReactNode;

  /**
   * Optional action buttons
   */
  actions?: React.ReactNode;
}

/**
 * Generic information card component
 */
export function InfoCard({ title, value, subtitle, icon, actions }: InfoCardProps) {
  return (
    <Card>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          {icon && <Box sx={{ mr: 2 }}>{icon}</Box>}
          <Typography variant="h6" component="div">
            {title}
          </Typography>
        </Box>
        <Typography variant="h4" component="div" sx={{ mb: 1 }}>
          {value}
        </Typography>
        {subtitle && (
          <Typography variant="body2" color="text.secondary">
            {subtitle}
          </Typography>
        )}
        {actions && <Box sx={{ mt: 2 }}>{actions}</Box>}
      </CardContent>
    </Card>
  );
}
