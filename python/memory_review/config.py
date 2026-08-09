"""Configuration for the CM-to-DataArchive memory review pipeline. [da-04r]

Single point of truth for paths, ports, thresholds and cursors. Nothing else in
the package hardcodes a path; every value below can be overridden by an
environment variable so a test run never touches production state.

Design context: /root/projects/COO/docs/specs/graduation-trigger-design.md
Delegation:     COO bead co-85xyp (Memory Review Pipeline)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default)).expanduser()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:  # never silently fall back to the default
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


class ConfigError(RuntimeError):
    """Raised when configuration is unusable. Never swallowed."""


# --- Repo roots ---------------------------------------------------------------

REPO_ROOT = _env_path("MR_REPO_ROOT", "/root/projects/DataArchive")
PROJECTS_ROOT = _env_path("MR_PROJECTS_ROOT", "/root/projects")
CLAUDE_PROJECTS_ROOT = _env_path("MR_CLAUDE_PROJECTS_ROOT", "/root/.claude/projects")

# --- Claude Monitor -----------------------------------------------------------

CM_BASE_URL = os.environ.get("MR_CM_BASE_URL", "http://localhost:3002")
CM_TIMEOUT_SECONDS = _env_int("MR_CM_TIMEOUT", 30)
CM_PAGE_SIZE = _env_int("MR_CM_PAGE_SIZE", 100)  # CM caps at maxPageSize=100

# --- Capture endpoint ---------------------------------------------------------
#
# 3000/3001 stay reserved-and-unused enterprise-wide [co-e591g]; 3002 is CM.
# 3010 is this pipeline's, and it binds loopback only.
ENDPOINT_HOST = os.environ.get("MR_ENDPOINT_HOST", "127.0.0.1")
ENDPOINT_PORT = _env_int("MR_ENDPOINT_PORT", 3010)

# --- Durable state ------------------------------------------------------------

DATA_DIR = _env_path("MR_DATA_DIR", str(REPO_ROOT / "data" / "memory-review"))
DB_PATH = _env_path("MR_DB_PATH", str(DATA_DIR / "review.db"))

# Tracked, append-only, git-visible record of every adjudication Steve makes.
# data/ is gitignored in this repo, so the operational store alone would be a
# single point of failure — this is the copy git carries.
LEDGER_DIR = _env_path("MR_LEDGER_DIR", str(REPO_ROOT / "memory-review" / "ledger"))
ADJUDICATION_LEDGER = LEDGER_DIR / "adjudications.jsonl"

# --- Observability ------------------------------------------------------------

MOO_STATE_DIR = _env_path("MR_STATE_DIR", "/var/moo/state")
MOO_LOG_DIR = _env_path("MR_LOG_DIR", "/var/moo/logs/memory-review")

COLLECT_HEARTBEAT = MOO_STATE_DIR / "memory-review-collect-heartbeat.json"
PACKET_HEARTBEAT = MOO_STATE_DIR / "memory-review-packet-heartbeat.json"
ENDPOINT_HEARTBEAT = MOO_STATE_DIR / "memory-review-endpoint-heartbeat.json"

# Heartbeat is stale past this age. 25h for the daily jobs so a run that slips an
# hour is not reported as a miss.
COLLECT_STALE_AFTER_SECONDS = _env_int("MR_COLLECT_STALE_AFTER", 25 * 3600)
PACKET_STALE_AFTER_SECONDS = _env_int("MR_PACKET_STALE_AFTER", 25 * 3600)
ENDPOINT_STALE_AFTER_SECONDS = _env_int("MR_ENDPOINT_STALE_AFTER", 900)

# --- Desk surface -------------------------------------------------------------
#
# The output path is a bookmark contract, not an accident — Steve parks a browser
# tab on it and refreshes in place. See tmuxMOO/bin/desk-html.sh [co-gsbnb].
DESK_DIR = _env_path("MR_DESK_DIR", "/var/moo/desk")
DESK_PAGE = DESK_DIR / "desk-memory-review.html"

# --- Analysis thresholds ------------------------------------------------------
#
# Every one of these is a tuning knob. They are NOT chosen by taste: each was set
# from the measured score distribution of the live corpus on 2026-08-09, sitting
# just above the 99th percentile of unrelated pairs so the sections carry signal
# rather than the top of a noise distribution. Measurements, for whoever retunes:
#
#   concept <-> concept       35,153 pairs · median 0.041 · p99 0.157 · max 1.000
#   concept <-> instruction   43,847 pairs · median 0.042 · p99 0.135 · max 0.583
#   utterance <-> utterance    4,645 pairs · median 0.056 · p99 0.354 · max 1.000
#
# They are recorded in the heartbeat and in every packet, so a packet's contents
# are always attributable to the thresholds that produced them.

# Character-trigram Jaccard, the `lexical` SimilarityIndex adapter.
TAU_COLLIDE = _env_float("MR_TAU_COLLIDE", 0.25)       # concept <-> concept topic collision
TAU_INSTRUCTION = _env_float("MR_TAU_INSTRUCTION", 0.15)  # concept <-> loaded instruction passage
TAU_ANCHOR = _env_float("MR_TAU_ANCHOR", 0.30)         # memory card <-> verbatim Steve utterance
# Absolute floor on distinctive words shared with an utterance before a memory
# may be labelled "Steve stated this". Ratio alone lets a five-word aside anchor
# a paragraph — measured 2026-08-09 on the live corpus.
ANCHOR_MIN_SHARED_TOKENS = _env_int("MR_ANCHOR_MIN_SHARED", 10)
# Floor on the inverse-document-frequency mass of the shared words. Two long
# texts share a dozen middling words by accident; a real restatement shares rare
# ones. Without this floor a Zgent-taxonomy concept anchored to Steve's
# commit-permissions message on twelve generic words (measured 2026-08-09).
ANCHOR_MIN_SHARED_RARITY = _env_float("MR_ANCHOR_MIN_RARITY", 4.0)
# At or above this score two texts are the same text — almost always an
# auto-memory card and the OKF concept graduated FROM it. Calibrated on the live
# corpus 2026-08-09: genuine unrelated-concept pairs sit at p99 = 0.157, while
# every card/concept graduation pair measured landed in 0.71-0.90. Shown fifteen
# times these bury the collisions that need a ruling, so the collision leg drops
# them and reports the count instead of the rows.
TAU_IDENTICAL = _env_float("MR_TAU_IDENTICAL", 0.70)
TAU_CLUSTER = _env_float("MR_TAU_CLUSTER", 0.35)       # utterance <-> utterance, graduation clusters
TAU_DISMISS = _env_float("MR_TAU_DISMISS", 0.28)       # tombstone suppression; deliberately looser

# The 3-strike rule, unchanged from the ratified April design.
STRIKE_MIN_OCCURRENCES = _env_int("MR_STRIKE_OCCURRENCES", 3)
STRIKE_MIN_SESSIONS = _env_int("MR_STRIKE_SESSIONS", 3)
STRIKE_MIN_DAY_SPREAD = _env_int("MR_STRIKE_DAY_SPREAD", 3)

# Governance caps, not performance caps: a hundred proposals is indistinguishable
# from zero, because both get ignored.
MAX_GRADUATION_CANDIDATES = _env_int("MR_MAX_GRADUATION", 5)
MAX_COLLISIONS = _env_int("MR_MAX_COLLISIONS", 15)
MAX_CONTRADICTIONS = _env_int("MR_MAX_CONTRADICTIONS", 15)
MAX_NEW_MEMORIES = _env_int("MR_MAX_NEW_MEMORIES", 40)

# Extraction filter band, per design §3.1. Below 40 chars is "yes"/"go on";
# above 4000 is a pasted document, not an utterance.
UTTERANCE_MIN_CHARS = _env_int("MR_UTTERANCE_MIN", 40)
UTTERANCE_MAX_CHARS = _env_int("MR_UTTERANCE_MAX", 4000)

# How far back a fresh install reaches on its first collection run.
BOOTSTRAP_LOOKBACK_DAYS = _env_int("MR_BOOTSTRAP_LOOKBACK_DAYS", 14)

# Input assertion: CM's corpus must have grown this recently or the run is
# degraded. A stale corpus behind a green pass is the exact defect this pipeline
# was told not to reproduce.
CORPUS_MAX_AGE_SECONDS = _env_int("MR_CORPUS_MAX_AGE", 24 * 3600)


@dataclass(frozen=True)
class Surface:
    """One repo's always-loaded instruction surface."""

    repo: str
    root: Path
    claude_md: Path
    rules_dir: Path

    def instruction_files(self) -> list[Path]:
        files: list[Path] = []
        if self.claude_md.is_file():
            files.append(self.claude_md)
        if self.rules_dir.is_dir():
            files.extend(sorted(self.rules_dir.glob("*.md")))
        return files


@dataclass(frozen=True)
class Bundle:
    """One OKF knowledge bundle. Read-only to this pipeline, always."""

    repo: str
    path: Path
    owner_note: str = ""


@dataclass
class Layout:
    """Everything the pipeline reads from, discovered once and asserted."""

    surfaces: list[Surface] = field(default_factory=list)
    bundles: list[Bundle] = field(default_factory=list)
    memory_dirs: list[Path] = field(default_factory=list)


# Bundles are named explicitly rather than discovered: a bundle has an owning
# zgent and a governance contract, and guessing which directories qualify would
# invent one. Add new bundles here, deliberately.
DEFAULT_BUNDLES = [
    ("COO", "conventions", "COO owns this bundle"),
    ("Strader", "knowledge", "Strader owns this bundle"),
]


def discover_layout(projects_root: Path | None = None,
                    claude_projects_root: Path | None = None) -> Layout:
    """Find every instruction surface, bundle and auto-memory store on this box.

    Discovery is deliberate about failure: it returns what it found, and the
    caller asserts the result is non-empty. An empty layout means the box moved
    under us, which is a failure, not an empty day.
    """
    projects_root = projects_root or PROJECTS_ROOT
    claude_projects_root = claude_projects_root or CLAUDE_PROJECTS_ROOT

    layout = Layout()

    if projects_root.is_dir():
        for child in sorted(projects_root.iterdir()):
            if not child.is_dir():
                continue
            claude_md = child / "CLAUDE.md"
            rules_dir = child / ".claude" / "rules"
            if claude_md.is_file() or rules_dir.is_dir():
                layout.surfaces.append(
                    Surface(repo=child.name, root=child,
                            claude_md=claude_md, rules_dir=rules_dir))

    for repo, rel, note in DEFAULT_BUNDLES:
        path = projects_root / repo / rel
        if path.is_dir():
            layout.bundles.append(Bundle(repo=repo, path=path, owner_note=note))

    if claude_projects_root.is_dir():
        for child in sorted(claude_projects_root.iterdir()):
            mem = child / "memory"
            if mem.is_dir():
                layout.memory_dirs.append(mem)

    return layout


def thresholds_snapshot() -> dict:
    """The tuning knobs in force, stamped into every heartbeat and packet."""
    return {
        "tau_collide": TAU_COLLIDE,
        "tau_instruction": TAU_INSTRUCTION,
        "tau_anchor": TAU_ANCHOR,
        "anchor_min_shared_tokens": ANCHOR_MIN_SHARED_TOKENS,
        "anchor_min_shared_rarity": ANCHOR_MIN_SHARED_RARITY,
        "tau_identical": TAU_IDENTICAL,
        "tau_cluster": TAU_CLUSTER,
        "tau_dismiss": TAU_DISMISS,
        "strike_min_occurrences": STRIKE_MIN_OCCURRENCES,
        "strike_min_sessions": STRIKE_MIN_SESSIONS,
        "strike_min_day_spread": STRIKE_MIN_DAY_SPREAD,
        "utterance_char_band": [UTTERANCE_MIN_CHARS, UTTERANCE_MAX_CHARS],
        "caps": {
            "graduation": MAX_GRADUATION_CANDIDATES,
            "collisions": MAX_COLLISIONS,
            "contradictions": MAX_CONTRADICTIONS,
            "new_memories": MAX_NEW_MEMORIES,
        },
    }


def ensure_dirs() -> None:
    """Create the directories the pipeline owns. Fails loudly if it cannot."""
    for path in (DATA_DIR, LEDGER_DIR, MOO_LOG_DIR, MOO_STATE_DIR, DESK_DIR):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConfigError(f"cannot create required directory {path}: {exc}") from exc


def describe() -> str:
    """Human-readable config dump for the operator and for run logs."""
    return json.dumps({
        "repo_root": str(REPO_ROOT),
        "cm_base_url": CM_BASE_URL,
        "endpoint": f"http://{ENDPOINT_HOST}:{ENDPOINT_PORT}",
        "db_path": str(DB_PATH),
        "ledger": str(ADJUDICATION_LEDGER),
        "desk_page": str(DESK_PAGE),
        "state_dir": str(MOO_STATE_DIR),
        "log_dir": str(MOO_LOG_DIR),
        "thresholds": thresholds_snapshot(),
    }, indent=2)
