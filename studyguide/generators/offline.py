"""A simple generator that works offline and never invents anything.

It only reuses wording from your slides:

* ``Term: meaning`` / ``Term - meaning`` / ``Term = meaning`` lines become a
  definition card and a reverse "which term?" card.
* Other bullet lines become fill-in-the-blank cards, hiding one key word.
  It prefers acronyms and technical-looking words.

The cards are basic, but every answer can be traced to a line on a slide.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from . import CardDraft, Generator, SlideText

BULLET = re.compile(r"^\s*(?:[•●○◦▪▫■□‣⁃∙·\-–—*>]+|\(?\d{1,2}[.)]|\(?[a-zA-Z][.)](?=\s))\s*")
DEFINITION = re.compile(r"^(?P<term>[^:=]{2,60}?)\s*(?::|=|\s[-–—]\s)\s*(?P<meaning>.{3,})$")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9'’\-]*[A-Za-z0-9]|[A-Za-z]")

STOPWORDS = set(
    """a about above after again against all also am an and any are as at be because been before
    being below between both but by can could did do does doing down during each few for from
    further had has have having he her here hers him his how i if in into is it its itself just
    may me might more most must my no nor not now of off on once only or other our out over own
    same she should so some such than that the their them then there these they this those
    through to too under until up very was we were what when where which while who whom why
    will with would you your yours called known used use using via per vs etc include includes
    including make makes made many much one two three like""".split()
)

MIN_CLOZE_WORDS = 4
BLANK = "_____"


def clean_lines(text: str) -> List[str]:
    lines = []
    for raw in text.splitlines():
        line = BULLET.sub("", raw).strip()
        line = re.sub(r"\s+", " ", line)
        if line:
            lines.append(line)
    return lines


def split_title(lines: List[str]) -> Tuple[Optional[str], List[str]]:
    """Treat a short first line without a full stop as the slide title."""
    if lines and len(lines[0]) <= 60 and not lines[0].endswith((".", ":")) and len(lines) > 1:
        return lines[0], lines[1:]
    return None, lines


def keyword_score(word: str, position: int, title_words: set) -> float:
    lower = word.lower()
    if lower in STOPWORDS or len(word) < 3 or lower in title_words:
        return -1
    score = min(len(word), 12) / 3
    if any(c.isdigit() for c in word):
        score += 2
    if word.isupper() and len(word) >= 2:
        score += 4  # acronym, e.g. ATP, DNA
    elif any(c.isupper() for c in word[1:]):
        score += 3  # e.g. mtDNA
    elif word[0].isupper() and position > 0:
        score += 2  # proper noun mid-sentence
    return score


def pick_keyword(line: str, title_words: set) -> Optional[re.Match]:
    best, best_score = None, 0.0
    for position, match in enumerate(WORD.finditer(line)):
        score = keyword_score(match.group(), position, title_words)
        if score > best_score:
            best, best_score = match, score
    return best


class OfflineGenerator(Generator):
    name = "offline-basic"

    def flashcards(self, slide: SlideText) -> List[CardDraft]:
        title, body = split_title(clean_lines(slide.text))
        heading = title or slide.topic
        title_words = {w.lower() for w in WORD.findall(title or "")}
        cards: List[CardDraft] = []
        for line in body:
            definition = DEFINITION.match(line)
            if definition and len(definition.group("term").split()) <= 6:
                term = definition.group("term").strip()
                meaning = definition.group("meaning").strip()
                cards.append(
                    CardDraft("definition", f"{heading}\n\nWhat does the slide say about “{term}”?", meaning, line)
                )
                if len(meaning.split()) >= 2:
                    cards.append(
                        CardDraft("reverse", f"{heading}\n\nWhich term is this?\n“{meaning}”", term, line)
                    )
                continue
            if len(WORD.findall(line)) < MIN_CLOZE_WORDS:
                continue
            keyword = pick_keyword(line, title_words)
            if keyword is None:
                continue
            blanked = line[: keyword.start()] + BLANK + line[keyword.end() :]
            cards.append(
                CardDraft("cloze", f"{heading}\n\nFill in the blank:\n{blanked}", keyword.group(), line)
            )
        return cards
