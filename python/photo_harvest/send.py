"""Send: Haiku descriptions through the Message Batches API. [co-06tcu]

The key is read from the vault file (/home/vault/DataArchive/env, written by
COO's vault-set.py) into memory and handed to the client; it is never logged,
printed, or exported to the environment.

One batch at a time: submit ready photos, wait, store each result by
custom_id (the photo's sha256), then delete the batch from Anthropic's service.
A spending stop, counted from the token totals on each result, refuses to
submit once the running cost would pass it.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sqlite3
import time
from pathlib import Path

from . import store
from .config import Config
from .prepare import work_path

log = logging.getLogger(__name__)

MODEL = "claude-haiku-5-5"
VAULT_FILE = Path(os.environ.get("PHOTO_HARVEST_VAULT", "/home/vault/DataArchive/env"))
KEY_NAME = "ANTHROPIC_API_KEY"

# Batch prices, USD per million tokens (Haiku 5.5 standard $0.10 / $0.50, halved
# for batches). From Anthropic's model table cached 2026-10-06; the spend stop
# uses them, so a price rise makes the stop conservative only if updated here.
PRICE_IN, PRICE_OUT = 0.05, 0.25

TAGS = [
    "people", "family gathering", "child", "pet", "house", "interior", "landscape",
    "water or boat", "vehicle", "food", "document or text", "screenshot", "event",
    "travel", "other",
]

SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string", "enum": TAGS}},
        "extra_tags": {"type": "array", "items": {"type": "string"}},
        "people": {"type": "integer"},
        "setting": {"type": "string", "enum": ["indoor", "outdoor", "unclear"]},
        "text_visible": {"type": "string"},
        "quality": {"type": "string", "enum": ["fine", "blurry", "dark", "duplicate-looking"]},
        "sensitive": {"type": "boolean"},
    },
    "required": ["description", "tags", "extra_tags", "people", "setting",
                 "text_visible", "quality", "sensitive"],
    "additionalProperties": False,
}

PROMPT = (
    "This photo comes from a family's personal archive. Describe it for a searchable "
    "catalog.\n"
    "- description: one plain sentence, 25 words or fewer, saying what is in the photo. "
    "Do not guess names, ages or places you cannot see.\n"
    "- tags: every tag from the list that applies.\n"
    "- extra_tags: up to three short words that would help find it, or none.\n"
    "- people: how many people are visible (0 if none).\n"
    "- setting: indoor, outdoor, or unclear.\n"
    "- text_visible: the visible words if short, 'yes' if long, or '' if none.\n"
    "- quality: fine, blurry, dark, or duplicate-looking.\n"
    "- sensitive: true if the photo shows nudity or anything else a family would "
    "consider private."
)


class SendError(RuntimeError):
    pass


def load_key(path: Path = VAULT_FILE) -> str:
    try:
        lines = path.read_text().splitlines()
    except OSError as exc:
        raise SendError(f"cannot read vault file {path}: {exc.strerror}") from None
    for line in lines:
        name, sep, value = line.strip().removeprefix("export ").partition("=")
        if sep and name.strip() == KEY_NAME and value.strip():
            return value.strip().strip('"').strip("'")
    raise SendError(f"{KEY_NAME} not found in {path}")


def client():
    import anthropic
    return anthropic.Anthropic(api_key=load_key(), max_retries=4)


def check() -> dict:
    """One tiny text request: proves the key works and the account has credit."""
    import anthropic
    try:
        msg = client().messages.create(
            model=MODEL, max_tokens=64, output_config={"effort": "low"},
            messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        )
    except anthropic.AuthenticationError as exc:
        return {"ok": False, "reason": "key rejected", "detail": exc.message}
    except anthropic.APIStatusError as exc:
        return {"ok": False, "reason": f"HTTP {exc.status_code}", "detail": exc.message}
    except anthropic.APIConnectionError as exc:
        return {"ok": False, "reason": "connection", "detail": str(exc)}
    text = next((b.text for b in msg.content if b.type == "text"), "")
    return {"ok": True, "model": msg.model, "reply": text.strip()[:20],
            "input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}


def build_request(sha256: str, image: Path):
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    data = base64.standard_b64encode(image.read_bytes()).decode()
    return Request(
        custom_id=sha256,
        params=MessageCreateParamsNonStreaming(
            model=MODEL,
            max_tokens=1024,  # thinking counts toward it; effort low keeps it small
            output_config={"effort": "low",
                           "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                             "data": data}},
                {"type": "text", "text": PROMPT},
            ]}],
        ),
    )


def spent(conn: sqlite3.Connection) -> float:
    i, o = conn.execute(
        "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0) FROM photo_harvest"
    ).fetchone()
    return i / 1e6 * PRICE_IN + o / 1e6 * PRICE_OUT


def apply_result(conn: sqlite3.Connection, result, cfg: Config) -> str:
    sha, r = result.custom_id, result.result
    if r.type != "succeeded":
        err = getattr(getattr(r, "error", None), "error", None)
        store.update(conn, sha, status="failed", batch_id=None,
                     error=f"{r.type}: {getattr(err, 'message', '')}"[:500])
        return "failed"
    msg = r.message
    usage = {"input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}
    if msg.stop_reason == "refusal":
        store.update(conn, sha, status="declined", error="model declined", **usage)
        return "declined"
    text = next((b.text for b in msg.content if b.type == "text"), "")
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        store.update(conn, sha, status="failed", batch_id=None,
                     error=f"unparseable ({msg.stop_reason})", **usage)
        return "failed"
    store.update(
        conn, sha, status="described", error=None,
        description=d["description"], tags_json=json.dumps(d["tags"] + d["extra_tags"][:3]),
        people=d["people"], setting=d["setting"], text_visible=d["text_visible"] or None,
        quality=d["quality"], model_sensitive=int(bool(d["sensitive"])), **usage,
    )
    work_path(cfg, sha).unlink(missing_ok=True)
    return "described"


def run_batch(cfg: Config, size: int, budget: float, poll: int = 60) -> dict:
    """Submit up to `size` ready photos as one batch, wait, store, delete."""
    api = client()
    with store.connect(cfg.db_path) as conn:
        already = spent(conn)
        # Worst case per photo: ~2,000 tokens in, the full 1,024 out.
        worst = size * (2000 / 1e6 * PRICE_IN + 1024 / 1e6 * PRICE_OUT)
        if already + worst > budget:
            raise SendError(f"spending stop: ${already:.2f} spent, a batch of {size} could "
                            f"reach ${already + worst:.2f}, over the ${budget:.2f} stop")
        rows = [r for r in store.by_status(conn, "ready", size)
                if work_path(cfg, r["sha256"]).is_file()]
        if not rows:
            return {"submitted": 0}
        requests = [build_request(r["sha256"], work_path(cfg, r["sha256"])) for r in rows]
        batch = api.messages.batches.create(requests=requests)
        for r in rows:
            store.update(conn, r["sha256"], status="submitted", batch_id=batch.id)
        conn.commit()
        log.info("batch %s submitted: %d photos", batch.id, len(rows))
        return collect(cfg, batch.id, poll, api=api)


def collect(cfg: Config, batch_id: str, poll: int = 60, api=None) -> dict:
    """Wait for a batch, store its results, delete it. Safe to re-run."""
    api = api or client()
    while True:
        b = api.messages.batches.retrieve(batch_id)
        if b.processing_status == "ended":
            break
        log.info("batch %s: %s, %d processing", batch_id, b.processing_status,
                 b.request_counts.processing)
        time.sleep(poll)
    tally: dict[str, int] = {}
    with store.connect(cfg.db_path) as conn:
        for result in api.messages.batches.results(batch_id):
            outcome = apply_result(conn, result, cfg)
            tally[outcome] = tally.get(outcome, 0) + 1
        conn.commit()
        cost = spent(conn)
    api.messages.batches.delete(batch_id)
    log.info("batch %s stored and deleted: %s", batch_id, tally)
    return {"batch": batch_id, **tally, "spent_total_usd": round(cost, 4)}
