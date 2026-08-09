"""Extraction: Steve's words, the memory tiers, and the always-loaded surface. [da-04r]

Three readers, one theme — separate what a **human** wrote from what a **machine**
wrote, because the whole point of the review packet is that COO's inferences and
Steve's statements are visually distinct.

1. `extract_utterance` — the filter cascade over CM's `role='user'` rows.
   `role='user'` is not "Steve said this": the overwhelming majority of those rows
   are tool results, system reminders, skill preambles and task notifications
   injected into the user channel by the harness. Design §3.1 measured this at
   ~4,285 human rows out of 37,857.
2. `read_memory_item` — auto-memory cards and OKF concepts. These are **machine
   prose**: an agent's distillation of what it believed. They are the inference
   candidates.
3. `segment_instructions` — CLAUDE.md and .claude/rules/*.md carved into passages.
   These are always-loaded and therefore outrank anything retrieved, which is the
   butterfly lesson: where knowledge sits outranks how well it is written.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from . import config

# --- 1. Utterance extraction --------------------------------------------------

# Machine text that arrives on the user channel. Anchored at the start of the
# content after stripping leading whitespace — a marker mentioned mid-sentence by
# a human talking *about* the harness is a real utterance and must survive.
_MACHINE_PREFIXES = (
    "[tool result",
    "[request interrupted",
    "<system-reminder>",
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<local-command-caveat>",
    "<task-notification>",
    "<teammate-message",
    "<user-prompt-submit-hook>",
    "<bash-input>",
    "<bash-stdout>",
    "<bash-stderr>",
    "caveat: the messages below",
    "another claude session sent a message",
    "background agent ",
    "2 background agents were stopped",
    "3 background agents were stopped",
    "base directory for this skill",
    "this session is being continued from a previous conversation",
    "api error",
    "the user opened the file",
)

# Substrings that mark the whole row as harness scaffolding wherever they appear.
_MACHINE_CONTAINS = (
    "<system-reminder>",
    "</command-name>",
    "<local-command-stdout>",
    "<local-command-caveat>",
    "is running…",
    "tool_use_id",
    "do not respond to these messages or otherwise consider them",
    '"idle_notification"',
    "is already loaded above; instructions unchanged",
    "was stopped by the user",
    "background agents were stopped by the user",
)

_IMAGE_ONLY_RE = re.compile(r"^\[image[^\]]*\]$", re.IGNORECASE)


@dataclass(frozen=True)
class Utterance:
    """One thing Steve actually typed or dictated, with its provenance."""

    content: str
    content_hash: str
    ts: str | None
    cm_conversation_id: int | None
    cm_conversation_uuid: str | None
    project: str | None
    entry_index: int | None
    role: str = "user"

    def as_row(self) -> dict:
        return {
            "content": self.content,
            "content_hash": self.content_hash,
            "ts": self.ts,
            "cm_conversation_id": self.cm_conversation_id,
            "cm_conversation_uuid": self.cm_conversation_uuid,
            "project": self.project,
            "entry_index": self.entry_index,
            "role": self.role,
        }


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def is_machine_text(content: str) -> bool:
    """True when this `role='user'` row was written by the harness, not by Steve."""
    if not content:
        return True
    stripped = content.strip()
    lowered = stripped.lower()
    if any(lowered.startswith(prefix) for prefix in _MACHINE_PREFIXES):
        return True
    if any(marker in lowered for marker in _MACHINE_CONTAINS):
        return True
    if _IMAGE_ONLY_RE.match(stripped):
        return True
    # A row that is nothing but a fenced block is pasted material, not speech.
    if stripped.startswith("```") and stripped.endswith("```"):
        return True
    return False


def extract_utterance(entry: dict, *,
                      conversation: dict | None = None,
                      min_chars: int | None = None,
                      max_chars: int | None = None) -> Utterance | None:
    """Apply the filter cascade to one CM entry. None means 'not Steve speaking'.

    Assistant turns are out of scope by design: mining them risks the system
    promoting COO's own restated opinions back into shared truth, which is
    strictly worse than missing something.
    """
    min_chars = config.UTTERANCE_MIN_CHARS if min_chars is None else min_chars
    max_chars = config.UTTERANCE_MAX_CHARS if max_chars is None else max_chars

    role = (entry.get("role") or "").strip().lower()
    if role != "user":
        return None

    content = entry.get("content")
    if not isinstance(content, str):
        return None
    content = content.strip()

    if is_machine_text(content):
        return None
    if not (min_chars <= len(content) <= max_chars):
        return None

    conversation = conversation or {}
    return Utterance(
        content=content,
        content_hash=content_hash(content),
        ts=entry.get("timestamp") or entry.get("ts"),
        cm_conversation_id=entry.get("conversation_id") or conversation.get("id"),
        cm_conversation_uuid=conversation.get("conversation_id"),
        project=conversation.get("project_name"),
        entry_index=entry.get("entry_index"),
    )


def extraction_report(entries: Iterable[dict]) -> dict:
    """Counts for the heartbeat: how much was dropped and by which stage.

    Reported on every run because a filter that suddenly drops everything looks
    identical to a quiet day unless the drop reasons are written down.
    """
    report = {"seen": 0, "not_user": 0, "machine_text": 0, "too_short": 0,
              "too_long": 0, "kept": 0}
    for entry in entries:
        report["seen"] += 1
        role = (entry.get("role") or "").strip().lower()
        if role != "user":
            report["not_user"] += 1
            continue
        content = entry.get("content")
        if not isinstance(content, str):
            report["machine_text"] += 1
            continue
        content = content.strip()
        if is_machine_text(content):
            report["machine_text"] += 1
        elif len(content) < config.UTTERANCE_MIN_CHARS:
            report["too_short"] += 1
        elif len(content) > config.UTTERANCE_MAX_CHARS:
            report["too_long"] += 1
        else:
            report["kept"] += 1
    return report


# --- 2. Memory tiers ----------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Minimal YAML-ish frontmatter reader: `key: value` and one nesting level.

    Deliberately not a YAML parser. The bundle's frontmatter contract is four
    scalar fields plus occasional lists; pulling in a YAML dependency to read
    that would be a dependency added for elegance, not need. Anything it cannot
    parse is left in the body rather than dropped.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    front: dict = {}
    current_list_key: str | None = None
    for raw_line in match.group(1).splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.lstrip().startswith("- ") and current_list_key:
            front.setdefault(current_list_key, [])
            if isinstance(front[current_list_key], list):
                front[current_list_key].append(line.lstrip()[2:].strip().strip('"\''))
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"\'')
        if value == "":
            front[key] = []
            current_list_key = key
        else:
            front[key] = value
            current_list_key = None

    return front, text[match.end():]


@dataclass(frozen=True)
class MemoryItem:
    """One auto-memory card or OKF concept, as collected."""

    kind: str            # auto-memory | okf-concept
    item_key: str
    repo: str | None
    source_path: str
    title: str | None
    description: str | None
    frontmatter: dict
    body: str
    body_hash: str
    mtime: str

    def as_row(self) -> dict:
        return {
            "kind": self.kind, "item_key": self.item_key, "repo": self.repo,
            "source_path": self.source_path, "title": self.title,
            "description": self.description, "frontmatter": self.frontmatter,
            "body": self.body, "body_hash": self.body_hash, "mtime": self.mtime,
        }

    def searchable_text(self) -> str:
        parts = [self.title or "", self.description or "", self.body]
        return "\n".join(p for p in parts if p).strip()


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)\
        .strftime("%Y-%m-%dT%H:%M:%SZ")


def read_memory_item(path: Path, kind: str, repo: str | None = None) -> MemoryItem | None:
    """Read one markdown card. None when the file is unreadable or empty."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if not text.strip():
        return None

    front, body = parse_frontmatter(text)
    title = front.get("title") or front.get("name")
    if not title:
        for line in body.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
    if not title:
        title = path.stem

    description = front.get("description")
    if not description:
        for line in body.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                description = stripped[:300]
                break

    return MemoryItem(
        kind=kind,
        item_key=f"{kind}:{path}",
        repo=repo,
        source_path=str(path),
        title=str(title)[:300],
        description=str(description or "")[:600] or None,
        frontmatter=front,
        body=body.strip(),
        body_hash=content_hash(body.strip()),
        mtime=_mtime_iso(path),
    )


def collect_memory_items(layout: config.Layout) -> Iterator[MemoryItem]:
    """Every auto-memory card and every OKF concept on this box.

    MEMORY.md is skipped in the auto-memory tier: it is an index of pointers, not
    a fact, and treating an index as a memory produces a permanent false
    collision against every card it lists.
    """
    for memory_dir in layout.memory_dirs:
        repo = memory_dir.parent.name
        for path in sorted(memory_dir.glob("*.md")):
            if path.name.upper() == "MEMORY.MD":
                continue
            item = read_memory_item(path, "auto-memory", repo)
            if item:
                yield item

    for bundle in layout.bundles:
        for path in sorted(bundle.path.rglob("*.md")):
            # index.md is the bundle's table of contents; log.md is the
            # append-only governance journal. Neither is a concept.
            if path.name.lower() in {"index.md", "log.md", "readme.md"}:
                continue
            item = read_memory_item(path, "okf-concept", bundle.repo)
            if item:
                yield item


# --- 3. The always-loaded surface --------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass(frozen=True)
class Passage:
    repo: str
    path: str
    heading: str | None
    start_line: int
    end_line: int
    text: str
    text_hash: str

    def as_row(self) -> dict:
        return {
            "repo": self.repo, "path": self.path, "heading": self.heading,
            "start_line": self.start_line, "end_line": self.end_line,
            "text": self.text, "text_hash": self.text_hash,
        }

    def location(self) -> str:
        return f"{self.path}#L{self.start_line}-{self.end_line}"


def segment_markdown(text: str, repo: str, path: str,
                     min_chars: int = 60, max_chars: int = 2500) -> list[Passage]:
    """Carve a markdown file into heading-scoped passages.

    Sections longer than `max_chars` are split on blank lines so a single long
    section cannot dominate every similarity comparison it takes part in.
    """
    lines = text.splitlines()
    passages: list[Passage] = []
    heading: str | None = None
    buffer: list[str] = []
    buffer_start = 1

    def flush(end_line: int) -> None:
        nonlocal buffer, buffer_start
        chunk = "\n".join(buffer).strip()
        buffer = []
        if len(chunk) < min_chars:
            return
        pieces = [chunk] if len(chunk) <= max_chars else _split_long(chunk, max_chars)
        offset = buffer_start
        for piece in pieces:
            if len(piece.strip()) < min_chars:
                continue
            piece_lines = piece.count("\n") + 1
            passages.append(Passage(
                repo=repo, path=path, heading=heading,
                start_line=offset, end_line=min(offset + piece_lines - 1, end_line),
                text=piece.strip(), text_hash=content_hash(piece.strip())))
            offset += piece_lines

    for idx, line in enumerate(lines, start=1):
        match = _HEADING_RE.match(line)
        if match:
            flush(idx - 1)
            heading = match.group(2).strip()
            buffer_start = idx
            buffer = [line]
            continue
        if not buffer:
            buffer_start = idx
        buffer.append(line)

    flush(len(lines))
    return passages


def _split_long(chunk: str, max_chars: int) -> list[str]:
    out: list[str] = []
    current: list[str] = []
    size = 0
    for block in chunk.split("\n\n"):
        if size + len(block) > max_chars and current:
            out.append("\n\n".join(current))
            current, size = [], 0
        current.append(block)
        size += len(block) + 2
    if current:
        out.append("\n\n".join(current))
    return out


def segment_instructions(layout: config.Layout) -> Iterator[Passage]:
    """Every passage of every always-loaded file, across every repo on the box."""
    for surface in layout.surfaces:
        for path in surface.instruction_files():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            yield from segment_markdown(text, surface.repo, str(path))


# --- Banned-phrase assertions (design addendum §C.3) --------------------------

_NEGATION_MARKERS = (
    "never ", "not ", "n't", "don't", "do not", "avoid ", "banned",
    "stop ", "wrong", "incorrect", "no longer", "instead of", "rather than",
)


def line_is_prohibition(line: str) -> bool:
    """True when a line states a phrase in order to forbid it.

    The 2026-08-05 butterfly fix put the ban itself into CLAUDE.md, so a naive
    grep flags the prohibition as the violation. This is a heuristic and it will
    miss prose that argues against a framing in running text without a negation
    word — that limitation is named in the design addendum §H.3 and is not
    papered over here.
    """
    stripped = line.strip().lower()
    if stripped.startswith(">") or stripped.startswith("|"):
        return True
    return any(marker in stripped for marker in _NEGATION_MARKERS)


def find_banned_phrases(phrases: Iterable[str], passages: Iterable[Passage]
                        ) -> list[dict]:
    """Deterministic leg: report each declared phrase found in a non-negated line."""
    wanted = [(p, p.lower().strip()) for p in phrases if p and p.strip()]
    if not wanted:
        return []
    hits: list[dict] = []
    for passage in passages:
        for line_offset, line in enumerate(passage.text.splitlines()):
            lowered = line.lower()
            for original, needle in wanted:
                if needle in lowered and not line_is_prohibition(line):
                    hits.append({
                        "phrase": original,
                        "repo": passage.repo,
                        "path": passage.path,
                        "line": passage.start_line + line_offset,
                        "text": line.strip()[:400],
                        "heading": passage.heading,
                    })
    return hits
