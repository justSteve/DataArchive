"""Configuration for the Photo Description Harvest. [co-06tcu]

Every path and threshold is here and can be overridden by an environment
variable, so a test run never touches production state.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    pass


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default)).expanduser()


def _env_num(name: str, default: float, kind=float):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return kind(raw)
    except ValueError as exc:  # never silently fall back to the default
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


PHOTO_EXTENSIONS = (".jpg", ".jpeg", ".heic")

# NudeNet classes that hold a photo back. Covered classes and faces never do.
SENSITIVE_CLASSES = frozenset({
    "FEMALE_BREAST_EXPOSED",
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "BUTTOCKS_EXPOSED",
    "ANUS_EXPOSED",
})


@dataclass(frozen=True)
class Config:
    db_path: Path
    harvest_root: Path
    # Other places harvested copies landed, each holding <drive_code>/ folders
    # (F:\Tera1A, F:\WWYY, F:\DVRC). Searched after harvest_root.
    alt_roots: tuple[Path, ...]
    manifest_dir: Path
    work_dir: Path
    min_bytes: int
    min_side: int
    max_side: int
    jpeg_quality: int
    # Low on purpose: a false hold costs one description, a miss sends a
    # sensitive photo out. Err toward holding.
    screen_threshold: float

    @classmethod
    def from_env(cls) -> "Config":
        repo = Path(__file__).resolve().parents[2]
        cfg = cls(
            db_path=_env_path("PHOTO_HARVEST_DB", str(repo / "data" / "archive.db")),
            harvest_root=_env_path("PHOTO_HARVEST_ROOT", "/mnt/z/Harvest"),
            alt_roots=tuple(Path(p) for p in os.environ.get(
                "PHOTO_HARVEST_ALT_ROOTS", "/mnt/f:/mnt/w").split(":") if p),
            manifest_dir=_env_path("PHOTO_HARVEST_MANIFESTS", str(repo / "Harvester" / "manifests")),
            work_dir=_env_path("PHOTO_HARVEST_WORK", "/var/moo/photo-harvest/work"),
            min_bytes=_env_num("PHOTO_HARVEST_MIN_BYTES", 20_000, int),
            min_side=_env_num("PHOTO_HARVEST_MIN_SIDE", 200, int),
            max_side=_env_num("PHOTO_HARVEST_MAX_SIDE", 1568, int),
            jpeg_quality=_env_num("PHOTO_HARVEST_JPEG_QUALITY", 85, int),
            screen_threshold=_env_num("PHOTO_HARVEST_SCREEN_THRESHOLD", 0.25),
        )
        if not 0 < cfg.screen_threshold < 1:
            raise ConfigError("PHOTO_HARVEST_SCREEN_THRESHOLD must be between 0 and 1")
        return cfg
