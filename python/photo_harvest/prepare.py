"""Prepare: make the copy that may be sent, keep the details that may not. [co-06tcu]

For each pending photo: open the original read-only, turn it upright from its
EXIF orientation, convert HEIC to RGB JPEG, shrink so the long side is at most
max_side, and save it with no metadata at all (no EXIF, no GPS, no ICC
profile, no comments). The photo's own date, camera and location are read
from the original and stored locally in photo_harvest.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError

from .config import Config

try:  # HEIC support; without it HEIC rows are recorded unreadable, not crashed
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

log = logging.getLogger(__name__)

_TAG = {v: k for k, v in ExifTags.TAGS.items()}
_GPS_IFD = 0x8825
_EXIF_IFD = 0x8769


class PrepareError(RuntimeError):
    pass


def _ratio(v) -> float:
    return float(v[0]) / float(v[1]) if isinstance(v, tuple) else float(v)


def _gps(gps: dict) -> tuple[float | None, float | None]:
    try:
        def deg(vals, ref):
            d, m, s = (_ratio(x) for x in vals)
            out = d + m / 60 + s / 3600
            return -out if ref in ("S", "W") else out
        return deg(gps[2], gps[1]), deg(gps[4], gps[3])
    except (KeyError, TypeError, ValueError, ZeroDivisionError, IndexError):
        return None, None


def read_details(img: Image.Image) -> dict:
    """The photo's own date, camera and location, for local storage only."""
    exif = img.getexif()
    if not exif:
        return {}
    sub = exif.get_ifd(_EXIF_IFD)
    taken = sub.get(_TAG["DateTimeOriginal"]) or exif.get(_TAG["DateTime"])
    make = (exif.get(_TAG["Make"]) or "").strip()
    model = (exif.get(_TAG["Model"]) or "").strip()
    lat, lon = _gps(exif.get_ifd(_GPS_IFD))
    out = {
        "taken_at": str(taken).strip() if taken else None,
        "camera": " ".join(p for p in (make, model) if p) or None,
        "gps_lat": lat,
        "gps_lon": lon,
    }
    return {k: v for k, v in out.items() if v is not None}


def prepare_one(source: Path, dest: Path, cfg: Config) -> dict:
    """Write the sendable copy to dest; return width, height and local details.

    Raises PrepareError for anything unreadable or below the size floor.
    """
    try:
        with open(source, "rb") as fh:
            head = fh.read(4096)
        # Some harvested copies (OneDrive placeholders) are all zero bytes.
        if head and not any(head):
            raise PrepareError("zero-filled file (an empty placeholder copy, not a photo)")
        with Image.open(source) as img:
            details = read_details(img)
            img = ImageOps.exif_transpose(img)
            if min(img.size) < cfg.min_side:
                raise PrepareError(f"too small: {img.size[0]}x{img.size[1]}")
            img = img.convert("RGB")
            img.thumbnail((cfg.max_side, cfg.max_side), Image.Resampling.LANCZOS)
            # A fresh image carries no info dict, so nothing rides along.
            clean = Image.new("RGB", img.size)
            clean.paste(img)
            dest.parent.mkdir(parents=True, exist_ok=True)
            clean.save(dest, "JPEG", quality=cfg.jpeg_quality, optimize=True)
            return {"width": clean.size[0], "height": clean.size[1], **details}
    except PrepareError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise PrepareError(f"{type(exc).__name__}: {exc}") from exc


def work_path(cfg: Config, sha256: str) -> Path:
    return cfg.work_dir / sha256[:2] / f"{sha256}.jpg"
