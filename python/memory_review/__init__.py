"""CM-to-DataArchive memory review pipeline. [da-04r]

Collects Claude Monitor's conversation corpus and the local memory tiers on a
daily cron, pre-processes them into a review packet, publishes that packet as an
interactive desk page, and records Steve's adjudications in a durable store.

The pipeline PROPOSES. No code path here writes to an OKF knowledge bundle —
bundle writes are bead-authorized per `.claude/rules/okf-memory.md`, and
`conventions/log.md` is append-only.

Delegated from COO bead co-85xyp. Design context:
`/root/projects/COO/docs/specs/graduation-trigger-design.md` and its addendum.
"""

__version__ = "1.0.0"
