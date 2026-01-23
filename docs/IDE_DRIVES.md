# Working with IDE Drives - Manual Drive Identification

## The Problem

When using USB-to-IDE adapters (or USB-to-SATA adapters), Windows typically sees the **adapter's identity** rather than the actual drive. This makes it impossible to track specific drives in your archive.

Example:
- What you see: "USB SATA/IDE Adapter"
- What you want: "Western Digital WD800BB 80GB"

## The Solution: Manual Specification

The DataArchive tool now supports manually specifying drive identity for cases where auto-detection doesn't work.

## Workflow for IDE Drives

### 1. Physical Inspection

Before connecting the drive, check the physical label:
- **Model number** (e.g., "WD800BB", "ST380011A")
- **Serial number** (usually a long alphanumeric code)
- **Capacity** (e.g., "80GB", "160GB")
- Any **physical markings** (stickers, labels, writing)

**TIP**: Take a photo of the drive label for your records!

### 2. Connect the Drive

1. Connect drive to your USB adapter
2. Wait for Windows to recognize it
3. Note which drive letter it gets assigned

### 3. Run Scan with Manual Identity

```bash
./dataarchive /mnt/e \
  --drive-model "Western Digital WD800BB 80GB" \
  --drive-serial "WD-WMAM12345678" \
  --drive-notes "Blue case sticker, from old Dell desktop"
```

### 4. Example with Different Scenarios

**Scenario A: Full info available from label**
```bash
./dataarchive /mnt/f \
  --drive-model "Seagate Barracuda ST3160023A 160GB" \
  --drive-serial "5JS2ABCD" \
  --drive-notes "IDE drive, 40-pin connector"
```

**Scenario B: Partial info (no serial visible)**
```bash
./dataarchive /mnt/g \
  --drive-model "Maxtor 6Y080L0 80GB" \
  --drive-notes "Green PCB, no visible serial number, drive #3 from pile"
```

**Scenario C: Completely unknown drive**
```bash
./dataarchive /mnt/h \
  --drive-notes "Unknown IDE drive, approximately 40GB, white label mostly worn off, found in basement box"
```

## Best Practices for IDE Drive Archival

### 1. Create a Physical Log

Keep a spreadsheet or notebook with:
| Photo | Model | Serial | Capacity | Physical Notes | Scan Date | Status |
|-------|-------|--------|----------|----------------|-----------|--------|
| IMG_001.jpg | WD800BB | WD-WMAM123 | 80GB | Blue sticker | 2025-10-07 | ✓ Scanned |

### 2. Label Drives After Scanning

Use a label maker or marker to add your own tracking:
- "ARCHIVED-001" 
- "Scanned 10/7/2025"
- "See database scan #42"

### 3. Photo Documentation

Before scanning, take photos showing:
- Drive label (close-up)
- Physical condition
- Any unique markings
- The drive in context (if from specific computer)

### 4. Group Related Drives

If you have multiple drives from the same source:
```bash
./dataarchive /mnt/e \
  --drive-model "Samsung SP0411N 40GB" \
  --drive-serial "S0BXJ1KP123456" \
  --drive-notes "Dell Dimension 3000, Drive 1 of 3, user: jsmith"
```

## Comparison: SATA vs IDE Strategies

### SATA Drives (Modern)
✅ **Best**: Direct motherboard connection
- Auto-detection works perfectly
- Fast transfer speeds
- Accurate identification

⚠️ **Acceptable**: USB adapter with manual spec
- When you can't open case
- For quick checks

### IDE Drives (Legacy)
✅ **Only Option**: USB adapter with manual specification
- Modern motherboards don't have IDE ports
- Always requires manual identity entry
- Physical documentation is critical

## Command Reference

### Full Syntax
```bash
./dataarchive <path> [OPTIONS]

Options:
  --drive-model TEXT      Drive model (e.g., "Samsung 870 EVO 250GB")
  --drive-serial TEXT     Drive serial number
  --drive-notes TEXT      Additional notes
  --db PATH               Database file (default: output/archive.db)
  --no-progress           Disable progress bar
```

### Examples

**Auto-detection (direct SATA):**
```bash
./dataarchive /mnt/e
```

**Manual specification (IDE or USB):**
```bash
./dataarchive /mnt/e --drive-model "WD800BB" --drive-serial "WD-WMAM12345"
```

**With extensive notes:**
```bash
./dataarchive /mnt/e \
  --drive-model "Maxtor DiamondMax 10 6L080M0" \
  --drive-serial "L40AFW4G" \
  --drive-notes "From IBM ThinkCentre, boot drive, Windows XP installed, green label with 'ACCOUNTING PC' written in marker"
```

## What Gets Stored

The database stores all provided information:
- Model name
- Serial number  
- Notes field (unlimited text)
- Scan date
- File inventory
- Size and filesystem info

You can query this later:
```sql
SELECT model, serial_number, notes, first_seen 
FROM drives 
WHERE notes LIKE '%ThinkCentre%';
```

## Tips for Large Collections

1. **Process in batches** - Do 5-10 drives per session
2. **Consistent naming** - Use same format for model names
3. **Photograph first** - Document before connecting
4. **Immediate labeling** - Mark drives right after scanning
5. **Backup database** - Copy archive.db regularly

## Safety Reminders

- 🔌 Static discharge: Touch case before handling drives
- 💾 Don't force connectors: IDE and SATA are keyed
- ⚡ Power off adapter when swapping drives
- 📝 Document as you go - don't rely on memory
- 💿 Old drives can fail - back up important finds immediately
