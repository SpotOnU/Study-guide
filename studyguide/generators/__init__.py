"""Study-material generators.

Everything that turns slide text into study material goes through a
``Generator``. Today there is one, ``OfflineGenerator``, which works entirely
on your Mac and only rearranges words that are already on your slides.

A smarter generator (a local AI model, or a cloud service you approve) can be
added later by writing another class with the same methods. Nothing else in
the app needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class SlideText:
    image_id: int
    topic: str
    rel_path: str
    text: str


@dataclass(frozen=True)
class CardDraft:
    kind: str  # "definition", "reverse" or "cloze"
    front: str
    back: str
    context: str  # the line of the slide the card came from


class Generator:
    name = "base"

    def flashcards(self, slide: SlideText) -> List[CardDraft]:
        raise NotImplementedError


def get_generator() -> Generator:
    from .offline import OfflineGenerator

    return OfflineGenerator()
