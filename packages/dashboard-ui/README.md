# @myorg/dashboard-ui

Shared dashboard UI framework with React and Material-UI components.

## Features

- ✅ Pre-styled dark theme for Material-UI
- ✅ DashboardLayout with AppBar and Container
- ✅ Generic InfoCard component
- ✅ TypeScript support with full type definitions
- ✅ React 18+ compatible

## Installation

### Local Development (file: protocol)

```json
{
  "dependencies": {
    "@myorg/dashboard-ui": "file:../../packages/dashboard-ui"
  }
}
```

### Published Package (when published to npm)

```json
{
  "dependencies": {
    "@myorg/dashboard-ui": "^1.0.0"
  }
}
```

## Usage

### DashboardLayout

Wraps your application with a consistent layout including AppBar and Container.

```typescript
import React from 'react';
import { DashboardLayout } from '@myorg/dashboard-ui';
import { Grid } from '@mui/material';

function App() {
  return (
    <DashboardLayout title="My Application">
      <Grid container spacing={3}>
        {/* Your content here */}
      </Grid>
    </DashboardLayout>
  );
}

export default App;
```

**Props:**
- `title: string` - Application title displayed in AppBar
- `children: React.ReactNode` - Main content
- `theme?: Theme` - Custom theme (optional, uses darkTheme by default)
- `maxWidth?: 'xs' | 'sm' | 'md' | 'lg' | 'xl' | false` - Container max width (default: 'xl')

### InfoCard

Generic card component for displaying information with optional icon and actions.

```typescript
import { InfoCard } from '@myorg/dashboard-ui';
import { StorageIcon } from '@mui/icons-material';

function SystemInfo() {
  return (
    <InfoCard
      title="Database"
      value="Connected"
      subtitle="Last updated: 5 minutes ago"
      icon={<StorageIcon />}
    />
  );
}
```

**Props:**
- `title: string` - Card title
- `value: string | number` - Main value to display
- `subtitle?: string` - Optional subtitle
- `icon?: React.ReactNode` - Optional icon
- `actions?: React.ReactNode` - Optional action buttons

### Dark Theme

Use the pre-configured dark theme in your application.

```typescript
import { ThemeProvider, CssBaseline } from '@mui/material';
import { darkTheme } from '@myorg/dashboard-ui';

function App() {
  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      {/* Your app content */}
    </ThemeProvider>
  );
}
```

### Custom Theme

You can also create your own theme based on the structure:

```typescript
import { createTheme } from '@mui/material/styles';

const myTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: { main: '#yourcolor' },
    // ... your customizations
  }
});
```

## Components Reference

### DashboardLayout

```typescript
interface DashboardLayoutProps {
  title: string;
  children: React.ReactNode;
  theme?: typeof darkTheme;
  maxWidth?: 'xs' | 'sm' | 'md' | 'lg' | 'xl' | false;
}
```

### InfoCard

```typescript
interface InfoCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
}
```

## Development

### Building

```bash
npm run build
```

### Watching

```bash
npm run watch
```

### Cleaning

```bash
npm run clean
```

## Peer Dependencies

This package requires the following peer dependencies:

```json
{
  "react": "^18.2.0",
  "react-dom": "^18.2.0"
}
```

Make sure these are installed in your project.

## License

MIT
