# DataArchive Deployment Guide

This guide explains how to deploy DataArchive in various environments, from local development to production servers.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development](#local-development)
3. [Production Build](#production-build)
4. [Deployment Scenarios](#deployment-scenarios)
5. [Configuration](#configuration)
6. [Troubleshooting](#troubleshooting)
7. [Maintenance](#maintenance)

## Prerequisites

### System Requirements

**Operating System:**
- Linux (Ubuntu 20.04+ recommended)
- Windows Subsystem for Linux (WSL 2)
- macOS (with PowerShell limitation)

**Software Dependencies:**
- Node.js 20.x or higher
- Python 3.6 or higher
- SQLite 3.x
- Git (for cloning)

**Hardware:**
- CPU: 2+ cores
- RAM: 4GB minimum, 8GB recommended
- Storage: 100MB application + database storage (varies by drive size)

### Access to Shared Packages

DataArchive depends on two shared packages:
- `@myorg/api-server` - Located at `/root/packages/api-server`
- `@myorg/dashboard-ui` - Located at `/root/packages/dashboard-ui`

**Build shared packages first:**
```bash
cd /root/packages/api-server
npm install
npm run build

cd /root/packages/dashboard-ui
npm install
npm run build
```

## Local Development

### Initial Setup

#### 1. Clone Repository

```bash
cd /root/projects
git clone <repository-url> data-archive
cd data-archive
```

#### 2. Install Dependencies

**TypeScript/Node.js:**
```bash
npm install --legacy-peer-deps
```

**Python:**
```bash
cd python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd ..
```

#### 3. Initialize Database

```bash
source python/venv/bin/activate
python3 -c "import sys; sys.path.insert(0, 'python'); from core.database import Database; Database('output/archive.db')"
deactivate
```

#### 4. Build TypeScript

```bash
npm run build
```

### Running Development Servers

**Option 1: Development Script (Recommended)**
```bash
chmod +x start-dev.sh
./start-dev.sh
```

**Option 2: Manual Start (Two Terminals)**

Terminal 1 - API Server:
```bash
npm run api
```

Terminal 2 - Frontend Dev Server:
```bash
npm run dev
```

### Access

- Frontend: http://localhost:5173
- API: http://localhost:3001
- Health Check: http://localhost:3001/api/health

## Production Build

### Build Process

#### 1. Build Backend

```bash
npm run build
```

This compiles TypeScript from `src/` to `dist/`.

#### 2. Build Frontend

```bash
npm run build:frontend
```

This creates optimized static files in `dist-frontend/`.

**Output:**
```
dist-frontend/
├── index.html
├── assets/
│   ├── index-[hash].js
│   ├── index-[hash].css
│   └── [other assets]
```

### Production File Structure

```
data-archive/
├── dist/              # Compiled backend JavaScript
├── dist-frontend/     # Static frontend files
├── python/            # Python domain logic
│   ├── venv/         # Virtual environment (built separately)
│   └── ...
├── output/            # Database directory
│   └── archive.db
├── package.json
└── node_modules/      # Production dependencies only
```

## Deployment Scenarios

### Scenario 1: Single-User Desktop Application

**Use Case**: Personal computer, local drive scanning

**Setup:**

1. Follow [Initial Setup](#initial-setup)
2. Run development script: `./start-dev.sh`
3. Access at http://localhost:5173

**Pros:**
- Simple setup
- No security concerns
- Full file system access

**Cons:**
- Manual startup required
- Not accessible remotely

### Scenario 2: Local Server with Systemd

**Use Case**: Always-on Linux server for personal/team use

#### Create Systemd Service

**File**: `/etc/systemd/system/dataarchive.service`

```ini
[Unit]
Description=DataArchive API Server
After=network.target

[Service]
Type=simple
User=dataarchive
WorkingDirectory=/opt/dataarchive
Environment="NODE_ENV=production"
Environment="PORT=3001"
ExecStart=/usr/bin/node /opt/dataarchive/dist/api/index.js
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### Setup Steps

```bash
# Create dedicated user
sudo useradd -r -s /bin/false dataarchive

# Deploy application
sudo mkdir -p /opt/dataarchive
sudo cp -r dist/ python/ output/ node_modules/ package.json /opt/dataarchive/
sudo chown -R dataarchive:dataarchive /opt/dataarchive

# Build Python venv in deployment location
cd /opt/dataarchive/python
sudo -u dataarchive python3 -m venv venv
sudo -u dataarchive ./venv/bin/pip install -r requirements.txt

# Enable and start service
sudo systemctl enable dataarchive
sudo systemctl start dataarchive
sudo systemctl status dataarchive
```

#### Serve Frontend with Nginx

**File**: `/etc/nginx/sites-available/dataarchive`

```nginx
server {
    listen 80;
    server_name dataarchive.yourdomain.com;

    root /opt/dataarchive/dist-frontend;
    index index.html;

    # Frontend static files
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy API requests
    location /api/ {
        proxy_pass http://localhost:3001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/dataarchive /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Scenario 3: Docker Container

**Use Case**: Isolated deployment, cloud hosting

#### Dockerfile

**File**: `Dockerfile`

```dockerfile
FROM node:20-slim

# Install Python and system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy application files
COPY package*.json ./
COPY dist/ ./dist/
COPY python/ ./python/
COPY output/ ./output/

# Install Node dependencies (production only)
RUN npm ci --omit=dev

# Setup Python virtual environment
WORKDIR /app/python
RUN python3 -m venv venv && \
    ./venv/bin/pip install --no-cache-dir -r requirements.txt

WORKDIR /app

# Expose API port
EXPOSE 3001

# Run API server
CMD ["node", "dist/api/index.js"]
```

#### Docker Compose

**File**: `docker-compose.yml`

```yaml
version: '3.8'

services:
  dataarchive-api:
    build: .
    ports:
      - "3001:3001"
    volumes:
      - ./output:/app/output
      - /mnt:/mnt:ro  # Mount drives read-only
    environment:
      - NODE_ENV=production
      - PORT=3001
      - DB_PATH=/app/output/archive.db
    restart: unless-stopped

  dataarchive-web:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./dist-frontend:/usr/share/nginx/html
      - ./nginx.conf:/etc/nginx/conf.d/default.conf
    depends_on:
      - dataarchive-api
    restart: unless-stopped
```

#### Build and Run

```bash
# Build
docker-compose build

# Run
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Scenario 4: Cloud Deployment (PM2)

**Use Case**: VPS, cloud server, multiple environments

#### Install PM2

```bash
npm install -g pm2
```

#### PM2 Ecosystem File

**File**: `ecosystem.config.js`

```javascript
module.exports = {
  apps: [
    {
      name: 'dataarchive-api',
      script: 'dist/api/index.js',
      instances: 2,
      exec_mode: 'cluster',
      env: {
        NODE_ENV: 'production',
        PORT: 3001,
        DB_PATH: './output/archive.db'
      },
      error_file: 'logs/api-error.log',
      out_file: 'logs/api-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      merge_logs: true
    }
  ]
};
```

#### Deploy with PM2

```bash
# Start
pm2 start ecosystem.config.js

# Save configuration
pm2 save

# Setup auto-start on boot
pm2 startup

# Monitor
pm2 monit

# View logs
pm2 logs dataarchive-api

# Restart
pm2 restart dataarchive-api

# Stop
pm2 stop dataarchive-api
```

## Configuration

### Environment Variables

Create `.env` file:

```env
# Server Configuration
NODE_ENV=production
PORT=3001
HOST=0.0.0.0

# Database
DB_PATH=./output/archive.db

# Python
PYTHON_PATH=./python/venv/bin/python3

# Logging
LOG_LEVEL=info

# CORS (if needed)
CORS_ORIGIN=http://localhost:5173
```

### Configuration File

**File**: `config/production.json`

```json
{
  "server": {
    "port": 3001,
    "host": "0.0.0.0"
  },
  "database": {
    "path": "./output/archive.db",
    "backupPath": "./output/backups"
  },
  "python": {
    "venvPath": "./python/venv/bin/python3",
    "scriptPath": "./python"
  },
  "scanning": {
    "maxConcurrentScans": 1,
    "batchSize": 100,
    "timeout": 3600000
  },
  "api": {
    "rateLimit": {
      "windowMs": 900000,
      "max": 100
    }
  }
}
```

## Security Hardening

### Production Checklist

- [ ] Change default ports
- [ ] Enable HTTPS (use Let's Encrypt)
- [ ] Implement authentication
- [ ] Enable rate limiting
- [ ] Restrict file system access
- [ ] Set up firewall rules
- [ ] Regular security updates
- [ ] Database backups
- [ ] Log rotation
- [ ] Monitor disk space

### HTTPS with Let's Encrypt

```bash
sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d dataarchive.yourdomain.com
```

### Firewall Configuration

```bash
# Allow SSH
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable
```

## Troubleshooting

### Issue: Port Already in Use

```bash
# Find process on port 3001
lsof -ti:3001

# Kill process
lsof -ti:3001 | xargs kill -9
```

### Issue: Database Locked

```bash
# Check for stale connections
fuser output/archive.db

# Kill stale processes
fuser -k output/archive.db
```

### Issue: Python Module Not Found

```bash
# Verify virtual environment
source python/venv/bin/activate
pip list

# Reinstall if needed
pip install -r python/requirements.txt
```

### Issue: Permission Denied

```bash
# Check file ownership
ls -la output/

# Fix permissions
sudo chown -R dataarchive:dataarchive output/
```

### Logs

**API Server Logs:**
```bash
# Development
npm run api (outputs to console)

# Production (systemd)
sudo journalctl -u dataarchive -f

# Production (PM2)
pm2 logs dataarchive-api

# Production (Docker)
docker-compose logs -f dataarchive-api
```

**Python Logs:**
```bash
# Check Python script output
tail -f output/scan.log
```

## Maintenance

### Database Backup

**Manual Backup:**
```bash
# Stop application first
sudo systemctl stop dataarchive

# Backup database
cp output/archive.db output/archive.db.backup-$(date +%Y%m%d)

# Restart application
sudo systemctl start dataarchive
```

**Automated Backup Script:**

**File**: `scripts/backup-db.sh`

```bash
#!/bin/bash
BACKUP_DIR="/opt/dataarchive/backups"
DB_PATH="/opt/dataarchive/output/archive.db"
DATE=$(date +%Y%m%d-%H%M%S)

mkdir -p $BACKUP_DIR
sqlite3 $DB_PATH ".backup '$BACKUP_DIR/archive-$DATE.db'"

# Keep only last 7 backups
ls -t $BACKUP_DIR/archive-*.db | tail -n +8 | xargs rm -f
```

**Cron Job:**
```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /opt/dataarchive/scripts/backup-db.sh
```

### Updates

**Update Application:**

```bash
# Pull latest code
git pull origin main

# Install dependencies
npm install --legacy-peer-deps

# Rebuild
npm run build
npm run build:frontend

# Restart service
sudo systemctl restart dataarchive
```

**Update Python Dependencies:**

```bash
source python/venv/bin/activate
pip install --upgrade -r python/requirements.txt
deactivate
```

### Monitoring

**Check Service Status:**
```bash
# Systemd
sudo systemctl status dataarchive

# PM2
pm2 status

# Docker
docker-compose ps
```

**Check Disk Space:**
```bash
df -h output/
du -sh output/archive.db
```

**Check Database Size:**
```bash
sqlite3 output/archive.db "SELECT
  (SELECT COUNT(*) FROM scans) as scans,
  (SELECT COUNT(*) FROM files) as files,
  (SELECT SUM(total_size_bytes) FROM scans) as total_bytes;"
```

### Performance Tuning

**SQLite Optimizations:**

```bash
# Analyze database
sqlite3 output/archive.db "ANALYZE;"

# Vacuum (reclaim space)
sqlite3 output/archive.db "VACUUM;"
```

**Node.js Optimizations:**

```bash
# Increase memory limit
export NODE_OPTIONS="--max-old-space-size=4096"
node dist/api/index.js
```

## Rollback Procedure

### In Case of Failed Deployment

```bash
# Stop service
sudo systemctl stop dataarchive

# Restore previous version
cd /opt/dataarchive
rm -rf dist/ dist-frontend/
mv dist.backup/ dist/
mv dist-frontend.backup/ dist-frontend/

# Restore database if needed
cp output/archive.db.backup output/archive.db

# Restart service
sudo systemctl start dataarchive
```

## Health Checks

### API Health Endpoint

```bash
curl http://localhost:3001/api/health
```

**Expected Response:**
```json
{
  "status": "ok",
  "timestamp": "2025-10-20T15:21:26.525Z",
  "uptime": 454.108664042,
  "database": true
}
```

### Monitoring Script

**File**: `scripts/health-check.sh`

```bash
#!/bin/bash
HEALTH_URL="http://localhost:3001/api/health"

response=$(curl -s -w "%{http_code}" $HEALTH_URL)
http_code=${response: -3}

if [ $http_code -eq 200 ]; then
    echo "✓ API is healthy"
    exit 0
else
    echo "✗ API is down (HTTP $http_code)"
    exit 1
fi
```

## Conclusion

DataArchive can be deployed in various configurations depending on your needs:

- **Development**: Simple `start-dev.sh` script
- **Single User**: Local server with manual start
- **Production**: Systemd service with Nginx reverse proxy
- **Containerized**: Docker Compose for isolation
- **Cloud**: PM2 for process management and clustering

Choose the deployment scenario that best fits your infrastructure and security requirements.

---

**Document Version**: 1.0
**Last Updated**: October 20, 2025
