"""Screen: a local nudity check before anything can be sent. [co-06tcu]

Runs NudeNet (an ONNX model bundled with the package, on this machine, no
network) over the prepared copy. Any exposed-body class at or above the
threshold holds the photo back: status held_sensitive, never sent anywhere.
The detector is a net, not a guarantee; the threshold is set low on purpose.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .config import SENSITIVE_CLASSES

log = logging.getLogger(__name__)


class Screener:
    def __init__(self, threshold: float, detector=None):
        self.threshold = threshold
        if detector is None:
            from nudenet import NudeDetector  # heavy import, deferred
            detector = NudeDetector()
        self._detector = detector

    def check(self, image_path: Path) -> tuple[bool, float, list[str]]:
        """Return (held, top sensitive score, sensitive classes found)."""
        hits = [
            d for d in self._detector.detect(str(image_path))
            if d.get("class") in SENSITIVE_CLASSES
        ]
        top = max((float(d.get("score", 0)) for d in hits), default=0.0)
        classes = sorted({d["class"] for d in hits if float(d.get("score", 0)) >= self.threshold})
        return top >= self.threshold, top, classes
