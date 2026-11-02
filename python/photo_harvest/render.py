"""Desk page of described photos: thumbnail, description, tags, location. [co-06tcu]

Held photos never appear, and neither does any photo Haiku marked sensitive.
Thumbnails are made from the original, 220 px, embedded in the page, so the
page needs nothing else to display.
"""

from __future__ import annotations

import base64
import html
import io
import json
from pathlib import Path

from PIL import Image, ImageOps

from . import store
from .config import Config

PAGE = Path("/var/moo/desk/desk-photo-harvest-pilot.html")

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:  # pragma: no cover
    pass


def thumb(path: str) -> str:
    try:
        with Image.open(path) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((220, 220))
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=70)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except OSError:
        return ""


def render(cfg: Config, out: Path = PAGE, limit: int = 300, drive: str | None = None,
           title: str = "Photo Harvest Pilot") -> Path:
    """drive limits the page to one source (IPHN: the 2026-11-02 iPhone import), newest first."""
    with store.connect(cfg.db_path) as conn:
        if drive:
            rows = conn.execute(
                """SELECT * FROM photo_harvest WHERE status = 'described'
                   AND COALESCE(model_sensitive, 0) = 0 AND drive_code = ?
                   ORDER BY taken_at IS NULL, taken_at DESC LIMIT ?""", (drive, limit)).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM photo_harvest WHERE status = 'described'
                   AND COALESCE(model_sensitive, 0) = 0
                   ORDER BY taken_at IS NULL, taken_at LIMIT ?""", (limit,)).fetchall()
        counts = store.counts(conn)
        tokens = conn.execute("SELECT SUM(input_tokens), SUM(output_tokens), COUNT(*) "
                              "FROM photo_harvest WHERE input_tokens IS NOT NULL").fetchone()
        flagged = conn.execute("SELECT COUNT(*) FROM photo_harvest WHERE model_sensitive = 1").fetchone()[0]
    cards = []
    for r in rows:
        tags = ", ".join(json.loads(r["tags_json"] or "[]"))
        meta = " · ".join(x for x in (
            (r["taken_at"] or "")[:10].replace(":", "-"), r["camera"] or "",
            f"{r['people']} people" if r["people"] else "", r["setting"] or "",
            r["quality"] if r["quality"] and r["quality"] != "fine" else "") if x)
        src = thumb(r["source_path"])
        cards.append(
            f'<figure><img loading="lazy" src="{src}" alt="">'
            f'<figcaption><p class="d">{html.escape(r["description"] or "")}</p>'
            f'<p class="t">{html.escape(tags)}</p><p class="m">{html.escape(meta)}</p>'
            f'<p class="p">{html.escape(r["source_path"])}</p></figcaption></figure>')
    tin, tout, n = tokens
    cost = ((tin or 0) / 1e6 * 0.05 + (tout or 0) / 1e6 * 0.25)
    summary = (f"{counts.get('described', 0)} described · {counts.get('held_sensitive', 0)} held by the local "
               f"screen (not shown, never sent) · {flagged} marked sensitive by Haiku (not shown) · "
               f"{counts.get('declined', 0)} declined · {counts.get('failed', 0)} failed · "
               f"average {(tin or 0) // max(n, 1):,} tokens in, {(tout or 0) // max(n, 1):,} out · "
               f"about ${cost:.3f} so far")
    out.write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{--bg:#fbfaf7;--fg:#1d1d1b;--mute:#6b6b66;--card:#fff;--line:#e4e1d8;--accent:#2f5d8a}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#161615;--fg:#ecebe6;--mute:#9a9992;--card:#1f1f1d;--line:#33322e;--accent:#8fb6dc}}}}
:root[data-theme="dark"]{{--bg:#161615;--fg:#ecebe6;--mute:#9a9992;--card:#1f1f1d;--line:#33322e;--accent:#8fb6dc}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif;padding:16px}}
h1{{font-size:1.4rem;margin:.2rem 0}} .s{{color:var(--mute);margin:0 0 1rem}}
main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}}
figure{{margin:0;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}}
img{{width:100%;height:200px;object-fit:cover;display:block;background:var(--line)}}
figcaption{{padding:8px 10px}} p{{margin:.2rem 0}} .d{{font-weight:500}}
.t{{color:var(--accent);font-size:.85rem}} .m,.p{{color:var(--mute);font-size:.78rem}} .p{{word-break:break-all}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p class="s">{f"{len(rows)} photos shown, newest first · " if drive else ""}{html.escape(summary)}</p>
<main>{''.join(cards)}</main>
</body></html>""", encoding="utf-8")
    out.chmod(0o644)
    return out
