"""Reading text from slide images.

The default engine uses Apple's Vision framework, which is built into macOS,
runs entirely on your Mac, and is free. Images are opened read-only and are
never uploaded anywhere.

On other systems (or if the pyobjc packages are missing) no OCR engine is
available. You can still type or paste transcripts by hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence


class OCRError(RuntimeError):
    pass


@dataclass
class TextBox:
    """One recognised line of text and its position.

    Coordinates are normalised 0..1 with the origin at the *top-left*.
    """

    text: str
    x: float
    y: float
    height: float


def order_lines(boxes: Sequence[TextBox]) -> str:
    """Put recognised lines in reading order: top-to-bottom, then left-to-right.

    Boxes whose vertical centres are within half a line height of each other
    are treated as being on the same row.
    """
    remaining = sorted(boxes, key=lambda b: (b.y + b.height / 2, b.x))
    rows: List[List[TextBox]] = []
    for box in remaining:
        centre = box.y + box.height / 2
        if rows:
            last = rows[-1]
            last_centre = sum(b.y + b.height / 2 for b in last) / len(last)
            tolerance = max(b.height for b in last + [box]) / 2
            if abs(centre - last_centre) <= tolerance:
                last.append(box)
                continue
        rows.append([box])
    lines = [" ".join(b.text for b in sorted(row, key=lambda b: b.x)) for row in rows]
    return "\n".join(line for line in lines if line.strip())


class OCREngine:
    name = "none"

    def recognize(self, path: Path) -> str:
        raise NotImplementedError


class AppleVisionOCR(OCREngine):
    """macOS Vision framework OCR via pyobjc. Runs locally on the Mac."""

    name = "apple-vision"

    def __init__(self) -> None:
        import Vision  # noqa: F401  (raises ImportError when unavailable)
        from Foundation import NSURL  # noqa: F401

    def recognize(self, path: Path) -> str:
        import objc
        import Vision
        from Foundation import NSURL

        with objc.autorelease_pool():
            url = NSURL.fileURLWithPath_(str(path))
            handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, None)
            request = Vision.VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
            request.setUsesLanguageCorrection_(True)
            ok, error = handler.performRequests_error_([request], None)
            if not ok:
                raise OCRError(f"Vision could not read {path.name}: {error}")
            boxes = []
            for observation in request.results() or []:
                candidates = observation.topCandidates_(1)
                if not candidates:
                    continue
                bb = observation.boundingBox()  # origin bottom-left, normalised
                boxes.append(
                    TextBox(
                        text=str(candidates[0].string()),
                        x=bb.origin.x,
                        y=1.0 - (bb.origin.y + bb.size.height),
                        height=bb.size.height,
                    )
                )
            return order_lines(boxes)


def default_engine() -> Optional[OCREngine]:
    """Return the best available local OCR engine, or None if there isn't one."""
    try:
        return AppleVisionOCR()
    except Exception:
        return None
