# Photo Triage — Vision-Based Photo Description

## Summary

Fast, batch photo description tool using Claude Haiku's vision API. Scans a directory of photos, generates a one-sentence description of each, and outputs a CSV. Designed for triaging large collections of poorly-named cell phone photos (Android/iPhone) where filenames like `20161203_142133.jpg` tell you nothing.

## Origin

Built 2026-03-21 in a gtOps COO session as a POC. Tested against `Z:\Backups\PhoneSteveBack\DCIM\Camera` — 20 JPGs from 2016-2017. 5/5 sample run succeeded with zero timeouts and zero unknowns.

## Architecture

Single Python script. No database — outputs CSV only. Uses the Anthropic SDK to send each photo to Haiku vision with a tightly scoped prompt:

- "Describe this photo in one sentence (15 words max)"
- "If unreadable, respond with exactly: UNKNOWN"
- `max_tokens: 60` keeps responses short and cheap
- Per-photo timeout (default 30s) catches stuck requests

## Cost

~$0.002 per photo with Haiku (~500 photos per dollar). The prompt + image runs ~1600 input tokens + ~30 output tokens per photo.

## Usage

```bash
# Activate a venv with anthropic installed
source /root/projects/DReader/.venv/bin/activate

# Full directory
python3 /root/projects/DataArchive/scripts/python/photo-triage.py /path/to/photos

# Sample first 10
python3 /root/projects/DataArchive/scripts/python/photo-triage.py /path/to/photos --sample 10

# Custom timeout and output
python3 /root/projects/DataArchive/scripts/python/photo-triage.py /path/to/photos --timeout 15 --output /tmp/results.csv
```

## Options

| Flag | Default | Description |
|---|---|---|
| `--timeout` | 30s | API timeout per photo |
| `--sample N` | all | Process only first N photos |
| `--output PATH` | `{photo_dir}/triage-results.csv` | Output CSV path |
| `--delay` | 0.2s | Delay between API calls |

## Output

CSV with columns: `file`, `description`, `status`, `path`

Status values: `ok` (described), `unknown` (unreadable), `timeout`, `error`

## API Key

Looks for `ANTHROPIC_API_KEY` in environment, then falls back to `.env` files in DReader and gtOps/myDesk.

## Lessons from POC

- Network drives (Z:) add latency to file reads — 10s timeout was too tight, 30s works
- Haiku vision is accurate enough for triage — pendant lights, dining setups, boats all correctly identified
- `UNKNOWN` prompt instruction is faster than relying on timeout for bad photos
- Supported formats: `.jpg`, `.jpeg`, `.png`, `.webp`, `.heic`
- `.mp4` files are ignored (filtered by extension)

## Next Steps

- Resume support (skip already-processed photos via existing CSV)
- Integration with DataArchive's existing scan/hash infrastructure
- Bulk rename suggestions based on descriptions
- Group similar photos by description similarity
