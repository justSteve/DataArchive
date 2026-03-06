# WD My Cloud Gen 1 → Debian/OMV Liberation Plan

**Target Device**: WD My Cloud WDBCTL0040HWT-00 (4TB Gen 1)
**Current Status**: Live production NAS at 192.168.0.11 (Z: drive)
**Current OS**: WD My Cloud OS3 (EOL, no upgrade path)
**Goal**: Replace with Debian/OpenMediaVault for full Linux control
**Primary Reference**: Fox_exe posts on WD community forums

## Current State Assessment

### Hardware
- **Model**: WD My Cloud Gen 1 (single bay)
- **Serial**: WCC4E7KFC7F4
- **MAC**: 00:90:A9:DA:45:9B
- **Drive**: Likely WD Green 4TB (WD40EZRX) or WD Red (~2013-2015)
- **Internal FS**: ext4
- **Network**: 192.168.0.11

### Access Status
- **SSH**: Available (requires `-oHostKeyAlgorithms=+ssh-rsa -oPubkeyAuthentication=no`)
- **Web UI**: Standard WD dashboard
- **SMB**: Active network shares
- **Physical**: Non-destructive opening confirmed (credit card method)

## Pre-Migration Checklist

### 1. Data Backup (CRITICAL)
**Before any OS replacement, ensure complete backup of Z: drive data**

- [ ] Inventory current Z: shares and content
- [ ] Calculate total data size on Z:
- [ ] Identify backup destination (E: drive? External USB?)
- [ ] Verify backup integrity
- [ ] Document current share structure and permissions
- [ ] Export any WD-specific configurations

**Command to check Z: drive usage:**
```bash
ssh sshd@192.168.0.11 -oHostKeyAlgorithms=+ssh-rsa -oPubkeyAuthentication=no "df -h /shares"
```

### 2. Research Phase
- [ ] Locate Fox_exe's Debian install guide for Gen 1 WD My Cloud
  - Search WD community forums for "Fox_exe gen1 debian"
  - Archive guide locally (forum posts can disappear)
- [ ] Review Debian/OMV compatibility with WD My Cloud Gen 1 hardware
- [ ] Identify required tools/media (USB drive, serial console?)
- [ ] Understand bootloader modification process
- [ ] Check for known hardware quirks (SATA, network, USB)

### 3. Risk Assessment
- [ ] Is the internal drive failing? (check SMART data via SSH)
- [ ] Can we recover if Debian install fails?
- [ ] Do we have physical access to open the case if needed?
- [ ] Is there a serial console access method?
- [ ] What's the rollback plan?

## Installation Plan

### Phase 1: Preparation (Non-Destructive)
1. **Full backup** of Z: drive data to safe location
2. **Document current state**:
   - Network configuration
   - Share definitions
   - User accounts
   - Any custom services
3. **Gather installation media**:
   - Debian ARM image (or OMV if direct install available)
   - USB drive for boot/install
   - Serial console adapter (if needed)
4. **Archive Fox_exe guides** locally

### Phase 2: Test Environment (Optional but Recommended)
If you have the extracted 4TB drive (currently at K:):
- [ ] Consider testing Debian install on extracted drive first
- [ ] Validate hardware compatibility
- [ ] Practice OMV setup
- [ ] Then swap into NAS chassis when confident

### Phase 3: Live Migration
**NOTE: This will wipe WD OS3. Ensure backups are complete!**

1. **Prepare NAS**:
   - Shut down gracefully via web UI
   - Disconnect from network (prevent accidental access during install)

2. **Install Debian/OMV** (following Fox_exe guide):
   - Boot from USB or modify bootloader
   - Install base Debian system
   - Configure network (static IP: 192.168.0.11)
   - Install OMV via apt

3. **Configure OMV**:
   - Set up web UI access
   - Configure Samba shares
   - Recreate share structure from backup
   - Set up user accounts

4. **Restore Data**:
   - Copy data from backup location back to shares
   - Verify file integrity
   - Test network access from Windows (Z: mapping)

### Phase 4: Enhanced Services (Post-Migration)
Once Debian/OMV is stable:
- [ ] Configure SSH for DataArchive zgent access
- [ ] Set up NFS (in addition to SMB)
- [ ] Consider Docker for containerized services
- [ ] Evaluate as persistent low-power zgent node
- [ ] Configure automated backups
- [ ] Set up monitoring (Prometheus/Grafana?)

## Key Decisions Needed

### 1. Backup Strategy
**Question**: Where will we backup ~2-3TB of Z: drive data before migration?
- **Option A**: E: drive (if space available)
- **Option B**: Extracted 4TB drive mounted temporarily
- **Option C**: Cloud backup (slow but safe)
- **Option D**: Another external drive

### 2. Test First or Live Migration?
**Question**: Should we test on the extracted drive first?
- **Pro**: Learn process, validate hardware, no risk to live data
- **Con**: Extra work, requires drive swapping

### 3. Debian vs. OMV Directly
**Question**: Install base Debian first, or go straight to OMV?
- **Debian first**: More control, understand the base system
- **OMV direct**: Faster to functional NAS, web UI immediately

### 4. Zgent Integration
**Question**: What role should this device play in the zgent ecosystem?
- Pure NAS (file storage only)
- Hybrid (NAS + lightweight always-on services)
- Docker host for containerized zgent agents
- DataArchive remote worker node

## Resources to Gather

### Primary
- [ ] Fox_exe Debian Gen 1 guide (WD community forums)
- [ ] OpenMediaVault documentation
- [ ] Debian ARM installation guide

### Hardware
- [ ] USB drive (8GB+) for boot media
- [ ] Serial console cable (if needed for recovery)
- [ ] Credit card or plastic pry tool (case opening)
- [ ] Torx screwdriver set (internal drive mounting)

### Backup
- [ ] Sufficient storage for Z: backup
- [ ] rsync or robocopy scripts for data transfer
- [ ] Checksum validation tools

## Timeline Estimate

**Conservative approach (recommended):**
- **Week 1**: Research, backup preparation, gather resources
- **Week 2**: Full backup and validation
- **Week 3**: Test install on extracted drive (optional)
- **Week 4**: Live migration to production NAS
- **Week 5**: Validation, optimization, zgent integration

**Aggressive approach (if confident):**
- **Day 1-2**: Research and backup
- **Day 3**: Live migration
- **Day 4-5**: Data restore and validation

## Success Criteria

Migration is successful when:
1. ✅ Debian/OMV boots reliably on WD hardware
2. ✅ Network accessible at 192.168.0.11
3. ✅ Web UI (OMV) accessible from Windows
4. ✅ SMB shares functional (Z: drive mapping works)
5. ✅ All backed-up data restored and verified
6. ✅ SSH access working for zgent integration
7. ✅ Performance equal or better than WD OS3
8. ✅ Can survive power cycle / reboot

## Rollback Plan

If migration fails:
1. **If WD OS backup exists**: Restore from WD firmware backup
2. **If data only**: Re-install WD OS3, restore shares manually
3. **If hardware failure**: Shuck drive, install in new enclosure
4. **If total loss**: Restore from backup to any available storage

## Next Immediate Actions

1. **SSH into live NAS** and check current state:
   ```bash
   ssh sshd@192.168.0.11 -oHostKeyAlgorithms=+ssh-rsa -oPubkeyAuthentication=no
   ```

2. **Inventory Z: drive contents**:
   - What shares exist?
   - How much data?
   - Critical vs. archival?

3. **Locate Fox_exe guide**:
   - Search WD community forums
   - Archive locally as PDF/markdown

4. **Decide backup strategy** based on data size and available storage

5. **Create bead** for WD liberation project in DataArchive

---

## DataArchive Zgent Integration Notes

**Potential roles for liberated NAS:**
- **Primary storage** for DataArchive consolidated files
- **Remote scanning node** (can scan itself + USB-attached drives)
- **Checkpoint storage** for long-running scan operations
- **Metrics/monitoring collector** (Prometheus on ARM)
- **Low-power always-on Docker host** for zgent services

**SSH access will enable:**
- Remote Python script execution
- File system scanning without network overhead
- Direct database operations (SQLite on NAS)
- Automated backup orchestration
- Integration with DataArchive API

---

**Status**: Planning phase
**Next Update**: After Fox_exe guide located and Z: inventory complete
**Owner**: DataArchive zgent
**Priority**: Medium (production device, careful approach required)
