# React Deduplication Fix for Shared Packages

## Problem

When using shared packages that include React dependencies (like `@myorg/dashboard-ui`), Vite may bundle multiple copies of React, causing this error:

```
Uncaught Error: A React Element from an older version of React was rendered.
This is not supported. It can happen if:
- Multiple copies of the "react" package is used.
- A library pre-bundled an old copy of "react" or "react/jsx-runtime".
```

## Symptoms

- **Blank screen** in browser
- **No visible errors** initially
- **Console warnings**: "Invalid prop `children` supplied to `ThemeProvider`, expected a ReactNode"
- **Console error**: "Multiple copies of the 'react' package is used"
- App works in development but crashes at runtime

## Root Cause

When your project depends on shared packages (via `file://` protocol) that have their own `node_modules/react`:

```
your-project/
├── node_modules/
│   └── react/              ← Your React
└── node_modules/@myorg/
    └── dashboard-ui/
        └── node_modules/
            └── react/      ← Shared package's React (CONFLICT!)
```

React **requires** a single instance in the entire application. Multiple copies break React's internal state management.

## The Fix

Update your `vite.config.ts` to force React deduplication:

### Before (Broken)

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  root: './src/frontend',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  server: {
    port: 5173
  }
});
```

### After (Fixed)

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  root: './src/frontend',
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      // ✅ Force all packages to use the same React instance
      'react': path.resolve(__dirname, './node_modules/react'),
      'react-dom': path.resolve(__dirname, './node_modules/react-dom'),
      'react/jsx-runtime': path.resolve(__dirname, './node_modules/react/jsx-runtime')
    },
    // ✅ Deduplicate React packages
    dedupe: ['react', 'react-dom']
  },
  server: {
    port: 5173
  }
});
```

## Key Changes

### 1. Add React Aliases

```typescript
resolve: {
  alias: {
    'react': path.resolve(__dirname, './node_modules/react'),
    'react-dom': path.resolve(__dirname, './node_modules/react-dom'),
    'react/jsx-runtime': path.resolve(__dirname, './node_modules/react/jsx-runtime')
  }
}
```

**What this does**: Forces all imports of `react`, `react-dom`, and `react/jsx-runtime` to resolve to your project's `node_modules` directory, not the shared package's copy.

### 2. Add Dedupe Configuration

```typescript
resolve: {
  dedupe: ['react', 'react-dom']
}
```

**What this does**: Tells Vite to deduplicate these packages during bundling, ensuring only one copy exists in the final bundle.

## When to Apply This Fix

Apply this fix to **any project** that:

✅ Uses Vite as the bundler
✅ Uses shared packages via `file://` protocol
✅ The shared packages depend on React/React-DOM
✅ You see blank screen or "multiple React copies" errors

## Verification Steps

After applying the fix:

1. **Restart the dev server** (required for config changes):
   ```bash
   # Kill existing servers
   lsof -ti:5173 | xargs kill -9

   # Restart
   npm run dev
   ```

2. **Hard refresh the browser**:
   - Windows/Linux: `Ctrl + Shift + R`
   - Mac: `Cmd + Shift + R`

3. **Check console** (F12):
   - Should have **no React errors**
   - Page should render correctly

## Other Frameworks

### Next.js Fix

For Next.js projects, update `next.config.js`:

```javascript
module.exports = {
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      'react': path.resolve(__dirname, 'node_modules/react'),
      'react-dom': path.resolve(__dirname, 'node_modules/react-dom'),
    };
    return config;
  },
};
```

### Webpack Fix

For vanilla Webpack projects, update `webpack.config.js`:

```javascript
module.exports = {
  resolve: {
    alias: {
      'react': path.resolve(__dirname, 'node_modules/react'),
      'react-dom': path.resolve(__dirname, 'node_modules/react-dom'),
    },
  },
};
```

## Alternative: Peer Dependencies (Better Long-term)

Instead of bundling React in shared packages, mark it as a **peer dependency**:

**In shared package's `package.json`:**

```json
{
  "peerDependencies": {
    "react": "^18.0.0 || ^19.0.0",
    "react-dom": "^18.0.0 || ^19.0.0"
  },
  "devDependencies": {
    "react": "^19.2.0",
    "react-dom": "^19.2.0"
  }
}
```

**Benefits**:
- Consumer projects provide React (no duplication)
- Smaller bundle size
- No version conflicts

**Trade-off**: Requires rebuilding shared packages when changing React versions.

## Troubleshooting

### Issue: Still seeing blank screen after fix

**Solution 1**: Clear Vite cache
```bash
rm -rf node_modules/.vite
npm run dev
```

**Solution 2**: Clear browser cache
- Hard refresh: `Ctrl + Shift + R`
- Or clear all browser data

### Issue: TypeScript errors after adding aliases

**Solution**: Update `tsconfig.json`:
```json
{
  "compilerOptions": {
    "paths": {
      "react": ["./node_modules/react"],
      "react-dom": ["./node_modules/react-dom"]
    }
  }
}
```

### Issue: Build works but production fails

**Solution**: Ensure aliases apply to both dev and build:
```typescript
export default defineConfig({
  resolve: {
    alias: { /* ... same aliases ... */ },
    dedupe: ['react', 'react-dom']
  },
  build: {
    // Explicitly set for production builds
    commonjsOptions: {
      include: [/node_modules/],
    }
  }
});
```

## Projects That Need This Fix

Apply to all projects using:
- `@myorg/dashboard-ui`
- `@myorg/api-server` (if it has React components)
- Any other shared packages with React dependencies

## Quick Checklist

Before deploying any Vite + shared package project:

- [ ] Added React aliases to `vite.config.ts`
- [ ] Added `dedupe: ['react', 'react-dom']`
- [ ] Restarted dev server
- [ ] Hard refreshed browser
- [ ] Verified no console errors
- [ ] Tested all pages/components
- [ ] Committed changes to Git

## Summary

**Problem**: Multiple React instances from shared packages
**Symptom**: Blank screen, React version errors
**Fix**: Add React deduplication to `vite.config.ts`
**Result**: Single React instance, working application

---

**Document Version**: 1.0
**Last Updated**: October 20, 2025
**Applies To**: Vite projects using shared packages with React
