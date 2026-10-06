"""Study-material generators.

Everything that turns slide text into study material goes through a
``Generator``, which returns ``StudyItem`` objects. Every item must pass
``validate.validate_item`` before it is saved, whichever generator made it.

Today there is one generator, ``OfflineGenerator``, which runs entirely on
your Mac. A smarter generator (a local AI model, or a cloud service you
approve) can be added later by implementing ``generate_topic``. Its output
goes through the same validation, so the quality rules stay the same.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

# Where an item's content comes from
SOURCE_SLIDE = "slide"  # answer and explanation come from the slide itself
SOURCE_CONTEXT = "context"  # question/explanation are added CompTIA context; the slide only mentions it


@dataclass(frozen=True)
class SlideText:
    image_id: int
    topic: str
    rel_path: str
    text: str


@dataclass
class StudyItem:
    image_id: int
    kind: str  # definition | term_mc | acronym | concept_mc | cloze
    concept: str  # the idea being tested, e.g. "Application software"
    prompt: str  # a self-contained question
    answer: str
    explanation: str  # teaches why the answer is correct
    source: str = SOURCE_SLIDE
    slide_support: str = ""  # the slide line(s) this item is based on or linked to
    added_context: str = ""  # background that did NOT come from the slide (labelled in the app)
    options: List[str] = field(default_factory=list)  # multiple choice, includes the answer
    why_wrong: Dict[str, str] = field(default_factory=dict)  # wrong option -> why it is wrong
    mentions: List[str] = field(default_factory=list)  # terms that must appear in slide_support

    def details(self) -> Dict:
        return {
            "concept": self.concept,
            "source": self.source,
            "added_context": self.added_context,
            "options": self.options,
            "why_wrong": self.why_wrong,
            "mentions": self.mentions,
        }


@dataclass
class Rejected:
    item: StudyItem
    problems: List[str]


@dataclass
class GenerationResult:
    items: List[StudyItem] = field(default_factory=list)
    rejected: List[Rejected] = field(default_factory=list)
    skipped_slides: List[str] = field(default_factory=list)  # not enough useful information


class Generator:
    name = "base"
    version = 0

    def generate_topic(
        self, slides: Sequence[SlideText], only_ids: Optional[set] = None
    ) -> GenerationResult:
        """Make validated study items for a topic.

        All slides are passed so related terms can be used as answer choices;
        ``only_ids`` limits which slides items are made for.
        """
        raise NotImplementedError


def get_generator() -> Generator:
    from .offline import OfflineGenerator

    return OfflineGenerator()
