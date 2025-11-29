/**
 * Main Application Component
 * Uses @myorg/dashboard-ui for layout
 */

import React, { useState } from 'react';
import { DashboardLayout } from '@myorg/dashboard-ui';
import { Grid, Box, Tabs, Tab } from '@mui/material';
import { DriveSelector } from './components/DriveSelector';
import { ScanProgress } from './components/ScanProgress';
import { ScanDashboard } from './components/ScanDashboard';
import { FileTree } from './components/FileTree';
import { LogViewer } from './components/LogViewer';
import { AdminPanel } from './components/AdminPanel';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`tabpanel-${index}`}
      aria-labelledby={`tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ pt: 3 }}>{children}</Box>}
    </div>
  );
}

function App() {
  const [tabValue, setTabValue] = useState(0);
  const [activeScanId, setActiveScanId] = useState<number | null>(null);
  const [selectedScanId, setSelectedScanId] = useState<number | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const handleScanStarted = (scanId: number) => {
    setActiveScanId(scanId);
    setRefreshTrigger(prev => prev + 1);
    setTabValue(1); // Switch to Monitor tab
  };

  const handleScanComplete = () => {
    setActiveScanId(null);
    setRefreshTrigger(prev => prev + 1);
  };

  const handleScanSelected = (scanId: number) => {
    setSelectedScanId(scanId);
    setTabValue(2); // Switch to Browse tab
  };

  return (
    <DashboardLayout title="DataArchive - Drive Cataloging System">
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
        <Tabs value={tabValue} onChange={handleTabChange}>
          <Tab label="New Scan" />
          <Tab label="Monitor" />
          <Tab label="Browse Scans" />
          <Tab label="Logs" />
          <Tab label="Admin" />
        </Tabs>
      </Box>

      {/* Tab 1: New Scan */}
      <TabPanel value={tabValue} index={0}>
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <DriveSelector onScanStarted={handleScanStarted} />
          </Grid>
          <Grid item xs={12} md={4}>
            <ScanDashboard
              onScanSelected={handleScanSelected}
              refreshTrigger={refreshTrigger}
            />
          </Grid>
        </Grid>
      </TabPanel>

      {/* Tab 2: Monitor Active Scan */}
      <TabPanel value={tabValue} index={1}>
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            {activeScanId ? (
              <ScanProgress
                scanId={activeScanId}
                onComplete={handleScanComplete}
              />
            ) : (
              <Box p={3} textAlign="center">
                No active scan. Start a new scan from the "New Scan" tab.
              </Box>
            )}
          </Grid>
          <Grid item xs={12} md={6}>
            <ScanDashboard
              onScanSelected={handleScanSelected}
              refreshTrigger={refreshTrigger}
            />
          </Grid>
        </Grid>
      </TabPanel>

      {/* Tab 3: Browse Scans */}
      <TabPanel value={tabValue} index={2}>
        <Grid container spacing={3}>
          <Grid item xs={12} md={4}>
            <ScanDashboard
              onScanSelected={handleScanSelected}
              refreshTrigger={refreshTrigger}
            />
          </Grid>
          <Grid item xs={12} md={8}>
            <FileTree scanId={selectedScanId} />
          </Grid>
        </Grid>
      </TabPanel>

      {/* Tab 4: Server Logs */}
      <TabPanel value={tabValue} index={3}>
        <Box sx={{ height: '70vh' }}>
          <LogViewer />
        </Box>
      </TabPanel>

      {/* Tab 5: Admin Panel */}
      <TabPanel value={tabValue} index={4}>
        <Box sx={{ maxWidth: 800 }}>
          <AdminPanel />
        </Box>
      </TabPanel>
    </DashboardLayout>
  );
}

export default App;
