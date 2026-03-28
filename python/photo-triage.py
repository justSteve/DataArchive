#!/usr/bin/env python3
"""
Photo Triage — Fast vision-based photo description using Claude Haiku.

Scans a directory of photos, sends each to Haiku vision for a one-line
description. Blurry/unreadable photos are tagged UNKNOWN and skipped fast.
Outputs a CSV with path, description, and status.

Usage:
    python3 photo-triage.py /path/to/photos
    python3 photo-triage.py /path/to/photos --timeout 5 --sample 10
"""

import anthropic
import base64
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}

MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/jpeg",  # heic gets converted or rejected — try as jpeg
}

PROMPT = """Describe this photo in one sentence (15 words max). Focus on the subject matter — what is this a photo OF?

If the image is too blurry, dark, overexposed, or otherwise impossible to identify, respond with exactly: UNKNOWN

No preamble. Just the description or UNKNOWN."""


def load_image_base64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def describe_photo(client, image_path: Path, timeout: float) -> tuple[str, str]:
    """Returns (description, status) where status is 'ok', 'unknown', or 'error'."""
    b64 = load_image_base64(image_path)
    ext = image_path.suffix.lower()
    media_type = MEDIA_TYPES.get(ext, "image/jpeg")

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": PROMPT},
                ],
            }],
            timeout=timeout,
        )
        text = response.content[0].text.strip()
        if text.upper() == "UNKNOWN":
            return text, "unknown"
        return text, "ok"

    except anthropic.APITimeoutError:
        return "TIMEOUT", "timeout"
    except anthropic.APIError as e:
        return f"ERROR: {e}", "error"
    except Exception as e:
        return f"ERROR: {e}", "error"


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Photo triage via Claude Haiku vision")
    parser.add_argument("photo_dir", help="Directory containing photos")
    parser.add_argument("--timeout", type=float, default=30.0, help="API timeout per photo in seconds (default: 30)")
    parser.add_argument("--sample", type=int, help="Process only N photos (for testing)")
    parser.add_argument("--output", "-o", help="Output CSV path (default: photo_dir/triage-results.csv)")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between API calls (default: 0.2s)")
    args = parser.parse_args()

    photo_dir = Path(args.photo_dir)
    if not photo_dir.is_dir():
        print(f"ERROR: {photo_dir} is not a directory")
        sys.exit(1)

    # Find photos
    photos = sorted([
        f for f in photo_dir.iterdir()
        if f.suffix.lower() in SUPPORTED_EXTENSIONS
    ])

    if not photos:
        print(f"No supported images found in {photo_dir}")
        sys.exit(1)

    print(f"\n─── Photo Triage ───")
    print(f"  Directory: {photo_dir}")
    print(f"  Photos:    {len(photos)}")
    print(f"  Timeout:   {args.timeout}s per photo")

    if args.sample:
        photos = photos[:args.sample]
        print(f"  Sample:    {args.sample} photos")

    est_cost = len(photos) * 0.002
    print(f"  Est. cost: ${est_cost:.2f}")
    print()

    # API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        for env_path in [
            Path("/root/projects/DReader/.env"),
            Path("/root/projects/gtOps/myDesk/.env"),
        ]:
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if "ANTHROPIC_API_KEY" in line and "=" in line:
                        api_key = line.split("=", 1)[1].strip().strip("'\"")
                        break
            if api_key:
                break

    if not api_key:
        print("ERROR: No ANTHROPIC_API_KEY found")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    # Output
    output_path = Path(args.output) if args.output else photo_dir / "triage-results.csv"
    results = []

    counts = {"ok": 0, "unknown": 0, "timeout": 0, "error": 0}

    for i, photo in enumerate(photos):
        print(f"  [{i+1}/{len(photos)}] {photo.name}...", end="", flush=True)
        desc, status = describe_photo(client, photo, args.timeout)
        counts[status] += 1
        results.append({"file": photo.name, "path": str(photo), "description": desc, "status": status})
        print(f" {desc}")

        if args.delay and i < len(photos) - 1:
            time.sleep(args.delay)

    # Write CSV
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "description", "status", "path"])
        writer.writeheader()
        writer.writerows(results)

    print(f"\n─── Results ───")
    print(f"  Described: {counts['ok']}")
    print(f"  Unknown:   {counts['unknown']}")
    print(f"  Timeout:   {counts['timeout']}")
    print(f"  Errors:    {counts['error']}")
    print(f"  Output:    {output_path}")


if __name__ == "__main__":
    main()
