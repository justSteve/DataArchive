# DataArchive Refactoring Plan
## Migration to Enterprise Architecture Pattern

**Version:** 1.0
**Date:** October 2025
**Reference Implementation:** Steve's Sites (Wayback Archive Toolkit)
**Blueprint:** ENTERPRISE_ARCHITECTURE_BLUEPRINT.md

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State Analysis](#current-state-analysis)
3. [Target Architecture](#target-architecture)
4. [Polyglot Design Strategy](#polyglot-design-strategy)
5. [5-Phase Migration Approach](#5-phase-migration-approach)
6. [Implementation Details](#implementation-details)
7. [Success Criteria](#success-criteria)

---

## Executive Summary

### Goal

Refactor DataArchive from a Python-only CLI/Flask application to a **polyglot architecture** that:
- Uses TypeScript/Node.js for infrastructure (Express API + React UI)
- Preserves Python for domain logic (drive scanning, validation, OS detection)
- Adopts the enterprise architecture blueprint pattern
- Provides a modern browser-based interface

### Key Principles

1. **Keep Python Domain Logic Intact**: The core scanning algorithms, drive validation, and OS detection remain in Python
2. **TypeScript Infrastructure Wrapper**: Express API server and React UI wrap and orchestrate Python scripts
3. **Two-Tier Architecture**: Leverage shared packages (`@myorg/api-server`, `@myorg/dashboard-ui`)
4. **Polyglot Integration**: TypeScript spawns Python processes and communicates via JSON/stdout

### Why This Approach?

- Python code is already working and tested
- No need to rewrite complex hardware detection logic in TypeScript
- Uniform browser interface across all enterprise projects
- Python can be gradually migrated to TypeScript over time (if needed)
- Best of both worlds: Python's rich ecosystem + TypeScript's type safety

---

## Current State Analysis

### What We Have (Python-Only)

```
DataArchive/
├── scan_drive.py           # CLI entry point - orchestrates 4-stage pipeline
├── archive_ui.py           # Flask web UI (to be replaced)
├── core/                   # Core domain logic (KEEP)
│   ├── file_scanner.py     # File system traversal
│   ├── database.py         # SQLite operations
│   ├── drive_manager.py    # WSL/PowerShell hardware detection
│   ├── drive_validator.py  # Pre-scan validation
│   ├── os_detector.py      # OS detection via filesystem
│   └── logger.py           # Logging
├── utils/
│   └── power_manager.py    # WSL sleep prevention
├── requirements.txt        # Python dependencies
└── venv/                   # Python virtual environment
```

### Current Strengths

✅ **Working Python domain logic**: Drive scanning, validation, OS detection all functional
✅ **WSL-specific hardware detection**: PowerShell queries for physical drive identity
✅ **SQLite database schema**: Well-designed with drives, scans, files, os_info tables
✅ **4-stage scan pipeline**: Clean separation of concerns

### Current Limitations

❌ **Flask UI is basic**: Limited interactivity, not aligned with enterprise patterns
❌ **No shared infrastructure**: Can't reuse across projects
❌ **CLI-only workflow**: No browser-based management interface
❌ **Python-only stack**: Doesn't match enterprise TypeScript infrastructure

---

## Target Architecture

### Final Structure (After Migration)

```
/root/
├── packages/                           # INFRASTRUCTURE TIER (shared)
│   ├── api-server/                    # @myorg/api-server (already exists)
│   └── dashboard-ui/                  # @myorg/dashboard-ui (already exists)
│
└── projects/
    └── data-archive/                  # DOMAIN TIER (new structure)
        ├── python/                    # Python domain logic (moved here)
        │   ├── core/
        │   │   ├── file_scanner.py
        │   │   ├── database.py
        │   │   ├── drive_manager.py
        │   │   ├── drive_validator.py
        │   │   ├── os_detector.py
        │   │   └── logger.py
        │   ├── utils/
        │   │   └── power_manager.py
        │   ├── scan_drive.py          # CLI entry point (callable from TS)
        │   └── requirements.txt
        │
        ├── src/                       # TypeScript infrastructure wrapper
        │   ├── domain/               # Domain capabilities (TypeScript wrappers)
        │   │   ├── scanning/         # Drive scanning capability
        │   │   │   ├── ScanOrchestrator.ts
        │   │   │   ├── PythonScanBridge.ts
        │   │   │   └── __tests__/
        │   │   ├── validation/       # Drive validation capability
        │   │   │   ├── DriveValidator.ts
        │   │   │   └── __tests__/
        │   │   ├── hardware/         # Hardware identity capability
        │   │   │   ├── HardwareIdentifier.ts
        │   │   │   └── __tests__/
        │   │   └── models/           # TypeScript types
        │   │       └── types.ts
        │   │
        │   ├── api/                  # API layer (Express routes)
        │   │   ├── routes/
        │   │   │   ├── scans.ts      # Scan management endpoints
        │   │   │   ├── drives.ts     # Drive discovery endpoints
        │   │   │   ├── files.ts      # File browsing endpoints
        │   │   │   └── status.ts     # Real-time scan status
        │   │   └── index.ts          # Uses @myorg/api-server
        │   │
        │   ├── frontend/             # React UI
        │   │   ├── components/
        │   │   │   ├── ScanDashboard.tsx
        │   │   │   ├── DriveSelector.tsx
        │   │   │   ├── ScanProgress.tsx
        │   │   │   ├── FileTree.tsx
        │   │   │   └── DriveDetails.tsx
        │   │   ├── App.tsx           # Uses @myorg/dashboard-ui
        │   │   └── theme.ts
        │   │
        │   ├── services/             # Infrastructure services
        │   │   ├── PythonBridge.ts   # Spawn Python processes
        │   │   ├── DatabaseService.ts # SQLite queries
        │   │   └── WebSocketService.ts # Real-time updates
        │   │
        │   └── utils/                # TypeScript utilities
        │       └── logger.ts
        │
        ├── package.json              # TypeScript dependencies
        ├── tsconfig.json
        ├── vite.config.ts            # Frontend bundling
        └── README.md
```

### Key Changes

1. **Python moves to `python/` subdirectory**: Domain logic preserved but reorganized
2. **TypeScript `src/` added**: Infrastructure wrapper around Python
3. **Uses shared packages**: `@myorg/api-server` and `@myorg/dashboard-ui` via file:// protocol
4. **Browser-based UI**: React replaces Flask
5. **RESTful API**: Express replaces Flask routes

---

## Polyglot Design Strategy

### Integration Pattern: Process Bridge

**Concept**: TypeScript spawns Python processes as subprocesses and communicates via JSON

```typescript
// TypeScript: src/services/PythonBridge.ts
import { spawn } from 'child_process';

export class PythonBridge {
  async scanDrive(drivePath: string): Promise<ScanResult> {
    return new Promise((resolve, reject) => {
      const python = spawn('python3', [
        './python/scan_drive.py',
        drivePath,
        '--json-output'  // Output as JSON for parsing
      ]);

      let output = '';
      python.stdout.on('data', (data) => {
        output += data.toString();
      });

      python.on('close', (code) => {
        if (code === 0) {
          resolve(JSON.parse(output));
        } else {
          reject(new Error(`Scan failed with code ${code}`));
        }
      });
    });
  }
}
```

```python
# Python: python/scan_drive.py (modified for JSON output)
import json
import sys

def main():
    # ... existing scan logic ...

    if '--json-output' in sys.argv:
        # Output structured JSON for TypeScript consumption
        result = {
            'scan_id': scan_id,
            'file_count': file_count,
            'total_size': total_size,
            'status': 'complete'
        }
        print(json.dumps(result))
    else:
        # Original CLI output
        logger.info(f"Scan complete: {file_count} files")
```

### Communication Strategies

**Strategy 1: JSON Output (for completed operations)**
- Python prints JSON to stdout
- TypeScript parses and uses
- Best for: scan initiation, validation, drive detection

**Strategy 2: Progress Updates (for long-running operations)**
- Python writes progress to shared file or database
- TypeScript polls or uses WebSocket to push to frontend
- Best for: file scanning progress

**Strategy 3: Database as Contract (for data sharing)**
- Both TypeScript and Python use same SQLite database
- Python writes, TypeScript reads
- Best for: querying scan results, file listings

### Advantages of This Approach

✅ **No rewrite needed**: Python code stays as-is
✅ **Type safety**: TypeScript layer provides types and validation
✅ **Modern UI**: React provides rich interactivity
✅ **Gradual migration**: Can port Python to TypeScript incrementally
✅ **Best tool for job**: Python for system ops, TypeScript for UI/API

---

## 5-Phase Migration Approach

### Phase 1: Bootstrap TypeScript Structure

**Goal**: Create TypeScript project structure and integrate shared packages

**Tasks**:
1. Create `/root/projects/data-archive/` directory (alongside DataArchive)
2. Initialize TypeScript project:
   ```bash
   cd /root/projects/data-archive
   npm init -y
   npm install --legacy-peer-deps
   ```
3. Add shared package dependencies to `package.json`:
   ```json
   {
     "dependencies": {
       "@myorg/api-server": "file:../../packages/api-server",
       "@myorg/dashboard-ui": "file:../../packages/dashboard-ui",
       "better-sqlite3": "^9.2.2",
       "axios": "^1.6.5"
     },
     "devDependencies": {
       "typescript": "^5.3.3",
       "vite": "^7.1.10",
       "@vitejs/plugin-react": "^5.0.4"
     }
   }
   ```
4. Create `tsconfig.json`, `vite.config.ts`
5. Create directory structure: `src/domain/`, `src/api/`, `src/frontend/`, `src/services/`

**Success Criteria**:
- Project builds with `npm run build`
- No TypeScript errors
- Shared packages linked correctly

---

### Phase 2: Move Python Code and Create Bridge

**Goal**: Relocate Python code and establish TypeScript-Python integration

**Tasks**:
1. Move Python code:
   ```bash
   mkdir -p /root/projects/data-archive/python
   cp -r /root/projects/DataArchive/core /root/projects/data-archive/python/
   cp -r /root/projects/DataArchive/utils /root/projects/data-archive/python/
   cp /root/projects/DataArchive/scan_drive.py /root/projects/data-archive/python/
   cp /root/projects/DataArchive/requirements.txt /root/projects/data-archive/python/
   ```

2. Create Python bridge service:
   ```typescript
   // src/services/PythonBridge.ts
   import { spawn } from 'child_process';
   import path from 'path';

   export class PythonBridge {
     private pythonPath = path.join(__dirname, '../../python');

     async scanDrive(drivePath: string, options: ScanOptions): Promise<ScanResult> {
       // Implementation as shown above
     }

     async validateDrive(drivePath: string): Promise<ValidationResult> {
       // Spawn python/core/drive_validator.py
     }

     async detectOS(drivePath: string): Promise<OSInfo> {
       // Spawn python/core/os_detector.py
     }
   }
   ```

3. Modify Python scripts to support JSON output:
   ```python
   # Add --json-output flag to scan_drive.py
   parser.add_argument('--json-output', action='store_true',
                       help='Output results as JSON')
   ```

4. Test Python bridge:
   ```typescript
   // src/services/__tests__/PythonBridge.test.ts
   describe('PythonBridge', () => {
     it('should scan drive and return results', async () => {
       const bridge = new PythonBridge();
       const result = await bridge.scanDrive('/mnt/e');
       expect(result.scan_id).toBeDefined();
     });
   });
   ```

**Success Criteria**:
- TypeScript can spawn Python processes
- JSON communication works bidirectionally
- Python scripts run successfully from TypeScript

---

### Phase 3: Build Express API Layer

**Goal**: Create RESTful API using shared `@myorg/api-server` package

**Tasks**:
1. Create API server using shared package:
   ```typescript
   // src/api/index.ts
   import { createApiServer, startServer } from '@myorg/api-server';
   import scansRouter from './routes/scans';
   import drivesRouter from './routes/drives';
   import filesRouter from './routes/files';

   const app = createApiServer({
     dbPath: './output/archive.db',
     enableLogging: true
   });

   app.use('/api/scans', scansRouter);
   app.use('/api/drives', drivesRouter);
   app.use('/api/files', filesRouter);

   startServer(app, 3001);
   ```

2. Create domain-specific routes:
   ```typescript
   // src/api/routes/scans.ts
   import { Router } from 'express';
   import { ScanOrchestrator } from '../../domain/scanning/ScanOrchestrator';

   const router = Router();
   const orchestrator = new ScanOrchestrator();

   // POST /api/scans/start
   router.post('/start', async (req, res) => {
     const { drivePath } = req.body;
     const scanId = await orchestrator.startScan(drivePath);
     res.json({ scanId });
   });

   // GET /api/scans/:id
   router.get('/:id', async (req, res) => {
     const scan = await orchestrator.getScanInfo(req.params.id);
     res.json(scan);
   });

   // GET /api/scans/:id/status
   router.get('/:id/status', async (req, res) => {
     const status = await orchestrator.getScanStatus(req.params.id);
     res.json(status);
   });

   export default router;
   ```

3. Create domain capability wrappers:
   ```typescript
   // src/domain/scanning/ScanOrchestrator.ts
   import { PythonBridge } from '../../services/PythonBridge';
   import { DatabaseService } from '../../services/DatabaseService';

   export class ScanOrchestrator {
     private bridge = new PythonBridge();
     private db = new DatabaseService();

     async startScan(drivePath: string): Promise<number> {
       // Validate drive first
       const validation = await this.bridge.validateDrive(drivePath);
       if (!validation.valid) {
         throw new Error('Drive validation failed');
       }

       // Start scan via Python
       const result = await this.bridge.scanDrive(drivePath);
       return result.scan_id;
     }

     async getScanInfo(scanId: number): Promise<ScanInfo> {
       return this.db.getScan(scanId);
     }

     async getScanStatus(scanId: number): Promise<ScanStatus> {
       // Check if scan is running, get progress
       const scan = await this.db.getScan(scanId);
       return {
         status: scan.status,
         filesProcessed: scan.file_count,
         progress: scan.progress
       };
     }
   }
   ```

**Success Criteria**:
- API endpoints respond correctly
- Can initiate scans via API
- Status updates work
- Database queries return data

---

### Phase 4: Build React Frontend

**Goal**: Create browser-based UI using shared `@myorg/dashboard-ui` package

**Tasks**:
1. Create main App component:
   ```typescript
   // src/frontend/App.tsx
   import React from 'react';
   import { DashboardLayout } from '@myorg/dashboard-ui';
   import { Grid } from '@mui/material';
   import { ScanDashboard } from './components/ScanDashboard';
   import { DriveSelector } from './components/DriveSelector';

   function App() {
     return (
       <DashboardLayout title="DataArchive - Drive Cataloging System">
         <Grid container spacing={3}>
           <Grid item xs={12} md={4}>
             <DriveSelector />
           </Grid>
           <Grid item xs={12} md={8}>
             <ScanDashboard />
           </Grid>
         </Grid>
       </DashboardLayout>
     );
   }

   export default App;
   ```

2. Create domain-specific components:
   ```typescript
   // src/frontend/components/ScanDashboard.tsx
   import React, { useState, useEffect } from 'react';
   import { Card, CardContent, Typography, List } from '@mui/material';
   import axios from 'axios';

   export function ScanDashboard() {
     const [scans, setScans] = useState([]);

     useEffect(() => {
       axios.get('/api/scans')
         .then(res => setScans(res.data))
         .catch(err => console.error(err));
     }, []);

     return (
       <Card>
         <CardContent>
           <Typography variant="h5">Recent Scans</Typography>
           <List>
             {scans.map(scan => (
               <ScanListItem key={scan.scan_id} scan={scan} />
             ))}
           </List>
         </CardContent>
       </Card>
     );
   }
   ```

3. Create interactive components:
   - `DriveSelector.tsx` - Select drive to scan
   - `ScanProgress.tsx` - Real-time progress bar
   - `FileTree.tsx` - Browse scan results
   - `DriveDetails.tsx` - Show drive hardware info

4. Set up Vite for development:
   ```typescript
   // vite.config.ts
   import { defineConfig } from 'vite';
   import react from '@vitejs/plugin-react';

   export default defineConfig({
     plugins: [react()],
     server: {
       proxy: {
         '/api': 'http://localhost:3001'
       }
     }
   });
   ```

**Success Criteria**:
- Frontend builds successfully
- Can view list of scans
- Can initiate new scan from UI
- Real-time progress updates work
- Can browse file tree

---

### Phase 5: Documentation and Polish

**Goal**: Comprehensive documentation for the polyglot architecture

**Tasks**:
1. Update README.md with new structure
2. Create ARCHITECTURE.md documenting TypeScript-Python integration
3. Update CLAUDE.md with new development workflows
4. Add inline code comments explaining Python bridge
5. Create development guide:
   ```markdown
   # Development Guide

   ## Setup

   ### Python Environment
   ```bash
   cd python
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

   ### TypeScript Environment
   ```bash
   npm install --legacy-peer-deps
   npm run build
   ```

   ## Running

   ### Development Mode
   ```bash
   # Terminal 1: API server
   npm run api

   # Terminal 2: Frontend dev server
   npm run dev
   ```

   ### Testing
   ```bash
   # TypeScript tests
   npm test

   # Python tests (if any)
   cd python && pytest
   ```
   ```

**Success Criteria**:
- Clear setup instructions
- Architecture well-documented
- Code is self-documenting
- Future developers can understand polyglot design

---

## Implementation Details

### Python Script Modifications

**Minimal changes needed**:

1. Add JSON output support to `scan_drive.py`:
   ```python
   def output_results(scan_id, file_count, total_size, format='text'):
       if format == 'json':
           print(json.dumps({
               'scan_id': scan_id,
               'file_count': file_count,
               'total_size': total_size,
               'status': 'complete'
           }))
       else:
           logger.info(f"Scan complete: {file_count} files")
   ```

2. Make scripts importable (add `if __name__ == '__main__':` guards)

3. Extract key functions for easier wrapping:
   ```python
   # Instead of:
   def main():
       # 500 lines of code

   # Refactor to:
   def validate_drive(path):
       # Validation logic
       return ValidationResult(...)

   def scan_drive(path, options):
       # Scan logic
       return ScanResult(...)

   def main():
       # CLI orchestration
       result = validate_drive(args.path)
       if result.valid:
           scan_drive(args.path, options)
   ```

### TypeScript Type Definitions

Create types matching Python data structures:

```typescript
// src/domain/models/types.ts

export interface DriveInfo {
  serial_number: string;
  model: string;
  size_bytes: number;
  filesystem: string;
  connection_type: string;
}

export interface ScanResult {
  scan_id: number;
  file_count: number;
  total_size: number;
  status: 'in_progress' | 'complete' | 'failed';
}

export interface FileInfo {
  file_id: number;
  path: string;
  size_bytes: number;
  modified_date: string;
  extension: string;
}

export interface OSInfo {
  os_type: string;
  os_name: string;
  version: string;
  boot_capable: boolean;
  confidence: string;
}
```

### Database Service

TypeScript wrapper for SQLite queries:

```typescript
// src/services/DatabaseService.ts
import Database from 'better-sqlite3';
import path from 'path';

export class DatabaseService {
  private db: Database.Database;

  constructor(dbPath = './output/archive.db') {
    this.db = new Database(dbPath);
  }

  getScans(): ScanInfo[] {
    const stmt = this.db.prepare(`
      SELECT s.*, d.model, d.serial_number
      FROM scans s
      JOIN drives d ON s.drive_id = d.drive_id
      ORDER BY s.scan_start DESC
    `);
    return stmt.all() as ScanInfo[];
  }

  getScan(scanId: number): ScanInfo | undefined {
    const stmt = this.db.prepare(`
      SELECT s.*, d.model, d.serial_number
      FROM scans s
      JOIN drives d ON s.drive_id = d.drive_id
      WHERE s.scan_id = ?
    `);
    return stmt.get(scanId) as ScanInfo | undefined;
  }

  getFiles(scanId: number, limit = 1000): FileInfo[] {
    const stmt = this.db.prepare(`
      SELECT * FROM files
      WHERE scan_id = ?
      LIMIT ?
    `);
    return stmt.all(scanId, limit) as FileInfo[];
  }
}
```

---

## Success Criteria

### Technical Success

✅ All tests passing (TypeScript + Python)
✅ API responds on http://localhost:3001
✅ Frontend accessible on http://localhost:5173
✅ Can initiate scan from browser
✅ Real-time progress updates working
✅ Can browse scan results in UI
✅ Database queries work from both TypeScript and Python

### Architectural Success

✅ Uses `@myorg/api-server` package via file:// protocol
✅ Uses `@myorg/dashboard-ui` for UI foundation
✅ Domain code organized by capability
✅ Clear separation: infrastructure (TS) vs domain (Python)
✅ Polyglot integration working smoothly

### Documentation Success

✅ README explains setup and usage
✅ ARCHITECTURE.md documents polyglot design
✅ CLAUDE.md updated for future instances
✅ Code has inline comments
✅ API endpoints documented

---

## Migration Timeline Estimate

- **Phase 1** (Bootstrap TypeScript): 1-2 days
- **Phase 2** (Python Bridge): 2-3 days
- **Phase 3** (Express API): 2-3 days
- **Phase 4** (React Frontend): 3-4 days
- **Phase 5** (Documentation): 1-2 days

**Total Estimate**: 9-14 days

---

## Next Steps

1. **Review this plan** with stakeholders
2. **Set up git worktree** (optional) for isolated development:
   ```bash
   git worktree add ../data-archive-refactor -b refactor/enterprise-architecture
   ```
3. **Start Phase 1**: Bootstrap TypeScript structure
4. **Iterate incrementally**: Each phase should be testable independently

---

## Questions & Considerations

**Q: Should we eventually port Python to TypeScript?**
A: Not necessary initially. Python handles system operations well. Port only if TypeScript advantages outweigh rewrite cost.

**Q: How do we handle Python virtual environment in production?**
A: Bundle Python scripts with dependencies or use Docker container with both Node.js and Python.

**Q: What about error handling across the bridge?**
A: Python exits with non-zero code on error. TypeScript catches stderr and exit code, maps to proper HTTP errors.

**Q: Can we use the same database from both languages?**
A: Yes! SQLite is file-based. Both can read/write. Use transactions for safety.

---

## Appendix: Command Reference

### Development Commands

```bash
# Install dependencies
npm install --legacy-peer-deps
cd python && pip install -r requirements.txt

# Build TypeScript
npm run build

# Run API server
npm run api

# Run frontend dev server
npm run dev

# Run tests
npm test

# Lint code
npm run lint
```

### Useful Scripts

Add to `package.json`:

```json
{
  "scripts": {
    "build": "tsc",
    "build:frontend": "vite build",
    "watch": "tsc --watch",
    "dev": "vite",
    "api": "node dist/api/index.js",
    "test": "jest",
    "lint": "eslint src/**/*.ts",
    "format": "prettier --write src/**/*.ts"
  }
}
```

---

**Document Version**: 1.0
**Last Updated**: October 2025
**Next Review**: After Phase 1 completion
