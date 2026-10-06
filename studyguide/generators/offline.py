"""Offline generator: concept first, then a question, then validation.

The old generator blanked out a "technical-looking" word in any line of four
or more words. That turned instructions and fragments such as "Find the
application you need" into meaningless cards. This version works differently:

1. Identify concepts on each slide (after removing footer text):
   * explicit definitions: "Term: meaning", "Term - meaning", "Term = meaning",
     "Term is a/an/the ..."
   * acronyms with their expansion: "NTFS (NT File System)"
   * CompTIA A+ Core 2 concepts the slide mentions (from the built-in concept
     bank; a generic word like "application" must be in the title or repeated)
   * complete statements about a key term ("BitLocker encrypts the entire volume")
2. For each concept, build candidate questions in order of preference.
3. Validate each candidate. A rejected candidate is replaced by the next one;
   if none pass, the concept is skipped. Slides without enough useful
   information produce no items.

Slide facts and added CompTIA context are kept apart: slide-based items quote
the slide; concept-bank items are marked as added context and only linked to
the slide line that mentions the concept.
"""

from __future__ import annotations

import random
import re
import zlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .. import cleanup
from ..knowledge.core2 import CONCEPTS, SOURCE_LABEL, Concept
from . import (
    SOURCE_CONTEXT,
    SOURCE_SLIDE,
    GenerationResult,
    Generator,
    Rejected,
    SlideText,
    StudyItem,
)
from .validate import BLANK, IMPERATIVES, RELATIONAL, norm, validate_item, words

BULLET = re.compile(r"^\s*(?:[•●○◦▪▫■□‣⁃∙·\-–—*>]+|\(?\d{1,2}[.)]|\(?[a-zA-Z][.)](?=\s))\s*")
DEF_SEP = re.compile(r"^(?P<term>[^:=–—]{2,60}?)\s*(?::|=|\s[-–—]\s)\s*(?P<meaning>.{3,})$")
DEF_IS = re.compile(
    r"^(?P<term>(?:[A-Z][\w+./-]*|[A-Z0-9]{2,})(?:\s+[\w+./-]+){0,4}?)\s+(?:is|are)\s+"
    r"(?P<meaning>(?:a|an|the)\s+.{3,})$"
)
ACR_AFTER = re.compile(r"\b(?P<acr>[A-Z][A-Za-z0-9]{1,6})\s*\((?P<exp>[A-Za-z][^()]{3,80})\)")
ACR_BEFORE = re.compile(r"(?P<exp>[A-Za-z][\w-]*(?:\s+[A-Za-z][\w-]*){1,9})\s*\((?P<acr>[A-Z][A-Za-z0-9]{1,6})\)")

GENERIC_TERMS = set(
    """pros cons example examples note notes benefit benefits advantage advantages disadvantage
    disadvantages tip tips warning why how what features feature use uses option options step steps
    summary overview introduction review more other others misc miscellaneous result results goal goals
    requirement requirements process""".split()
)
SMALL_WORDS = {"of", "and", "the", "for", "to", "in", "on", "a", "an", "with", "by", "or"}

MAX_ITEMS_PER_SLIDE = 5
MAX_ITEMS_PER_CONCEPT = 2  # e.g. a definition question and a "which term" question


# --------------------------------------------------------------------------
# Step 1: understand the slide
# --------------------------------------------------------------------------


@dataclass
class Definition:
    term: str
    meaning: str
    line: str


@dataclass
class Acronym:
    acronym: str
    expansion: str
    line: str


@dataclass
class Mention:
    concept: Concept
    alias: str
    line: str
    in_title: bool


@dataclass
class ParsedSlide:
    slide: SlideText
    title: Optional[str]
    lines: List[str]
    text: str  # cleaned text (no footer)
    definitions: List[Definition] = field(default_factory=list)
    acronyms: List[Acronym] = field(default_factory=list)
    mentions: List[Mention] = field(default_factory=list)
    statements: List[Tuple[str, str]] = field(default_factory=list)  # (term, line)

    @property
    def context(self) -> str:
        return self.title or self.slide.topic


def clean_lines(text: str) -> List[str]:
    text, _ = cleanup.clean_text(text, cleanup.ALWAYS)  # footers never become study content
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", BULLET.sub("", raw)).strip()
        if line:
            lines.append(line)
    return lines


def valid_term(term: str) -> bool:
    ws = term.split()
    if not ws or len(ws) > 6 or not re.search(r"[A-Za-z]", term):
        return False
    if term.lower() in GENERIC_TERMS or ws[0].lower() in IMPERATIVES:
        return False
    return ws[-1].lower() not in SMALL_WORDS


def is_real_definition(meaning: str) -> bool:
    """A definition needs real words, not just a number or a measurement ("4 GB maximum")."""
    ws = words(meaning)
    alpha = [w for w in ws if re.fullmatch(r"[A-Za-z][A-Za-z'’-]{2,}", w)]
    return len(ws) >= 3 and len(alpha) >= 2 and not re.match(r"\d", meaning)


def initials_match(acronym: str, expansion: str) -> bool:
    letters = "".join(ch for ch in acronym.lower() if ch.isalpha())
    initials = "".join(
        (w[0] + "".join(ch for ch in w[1:] if ch.isupper())).lower()
        for w in expansion.split() if w.lower() not in SMALL_WORDS
    )
    return bool(letters) and initials.startswith(letters[:1]) and _is_subsequence(letters, initials)


def _is_subsequence(needle: str, hay: str) -> bool:
    it = iter(hay)
    return all(ch in it for ch in needle)


def find_acronyms(line: str) -> List[Acronym]:
    found = []
    for m in ACR_AFTER.finditer(line):
        acr, exp = m.group("acr"), m.group("exp").strip()
        if acr.upper() == acr and initials_match(acr, exp):
            found.append(Acronym(acr, exp, line))
    for m in ACR_BEFORE.finditer(line):
        acr = m.group("acr")
        if acr.upper() != acr:
            continue
        ws = m.group("exp").split()
        for k in range(1, len(ws) + 1):  # shortest trailing run of words that matches
            exp = " ".join(ws[-k:])
            if len([w for w in ws[-k:] if w.lower() not in SMALL_WORDS]) >= len(acr) - 1 and \
                    initials_match(acr, exp):
                found.append(Acronym(acr, exp, line))
                break
    return found


def _alias_pattern(alias: str, case_sensitive: bool) -> re.Pattern:
    return re.compile(r"(?<![\w-])" + re.escape(alias) + r"(?![\w-])", 0 if case_sensitive else re.IGNORECASE)


def find_mentions(title: Optional[str], lines: List[str]) -> List[Mention]:
    mentions = []
    all_text = "\n".join(lines)
    for concept in CONCEPTS:
        hit = None
        for alias in concept.aliases + concept.generic_aliases:
            pattern = _alias_pattern(alias, alias in concept.case_sensitive)
            occurrences = len(pattern.findall(all_text))
            if not occurrences:
                continue
            in_title = bool(title and pattern.search(title))
            if alias in concept.generic_aliases and not in_title and occurrences < 2:
                continue  # an everyday word used in passing isn't enough
            body = [ln for ln in lines if ln != title and pattern.search(ln)]
            hit = Mention(concept, pattern.search(all_text).group(), body[0] if body else title, in_title)
            break
        if hit:
            mentions.append(hit)
    return mentions


def parse_slide(slide: SlideText) -> ParsedSlide:
    lines = clean_lines(slide.text)
    title = None
    if len(lines) > 1 and len(lines[0]) <= 60 and not lines[0].endswith((".", ":")) \
            and not DEF_SEP.match(lines[0]):
        title = lines[0]
    parsed = ParsedSlide(slide, title, lines, "\n".join(lines))
    body = lines[1:] if title else lines
    for line in body:
        m = DEF_SEP.match(line) or DEF_IS.match(line)
        if m:
            term, meaning = m.group("term").strip(), m.group("meaning").strip().rstrip(".")
            if valid_term(term) and is_real_definition(meaning):
                parsed.definitions.append(Definition(term, meaning, line))
        parsed.acronyms.extend(find_acronyms(line))
    parsed.mentions = find_mentions(title, lines)

    key_terms = {d.term for d in parsed.definitions} | {a.acronym for a in parsed.acronyms}
    key_terms |= {m.alias for m in parsed.mentions if m.alias.lower() not in GENERIC_TERMS}
    for line in body:
        for term in sorted(key_terms, key=len, reverse=True):
            m = re.match(re.escape(term) + r"\s+(\w+)", line, re.IGNORECASE)
            if m and m.group(1).lower() in RELATIONAL and len(words(line)) >= 6 \
                    and not DEF_SEP.match(line):
                parsed.statements.append((line[: len(term)], line))
                break
    return parsed


# --------------------------------------------------------------------------
# Step 2: candidate questions for each concept, in order of preference
# --------------------------------------------------------------------------


def _shuffle(options: List[str], seed: str) -> List[str]:
    out = list(options)
    random.Random(zlib.crc32(seed.encode())).shuffle(out)
    return out


def _concept_for_term(term: str) -> Optional[Concept]:
    t = norm(term)
    for concept in CONCEPTS:
        if t in {norm(a) for a in concept.aliases} or t == norm(concept.term):
            return concept
    return None


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def definition_candidates(p: ParsedSlide, d: Definition, topic_defs: List[Definition]) -> List[StudyItem]:
    image_id, ctx = p.slide.image_id, p.context
    bank = _concept_for_term(d.term)
    added = (f"{SOURCE_LABEL}: {bank.explanation}" if bank else "")
    technical = bool(re.search(r"[A-Z]{2,}|\d", d.term)) or d.term[:1].isupper()
    out = []

    # Which term matches this description? (multiple choice, alternatives from the same topic)
    others = [o for o in topic_defs if norm(o.term) != norm(d.term) and valid_term(o.term)]
    seen, distinct = set(), []
    for o in others:
        if norm(o.term) not in seen:
            seen.add(norm(o.term))
            distinct.append(o)
    if len(distinct) >= 2:
        picked = distinct[:3]
        options = _shuffle([d.term] + [o.term for o in picked], d.term + d.meaning)
        out.append(StudyItem(
            image_id, "term_mc", d.term,
            prompt=f"In {p.slide.topic}, which term is defined as “{d.meaning}”?",
            answer=d.term,
            explanation=f"Your {ctx} notes define {d.term} as “{d.meaning}”, so {d.term} is the term "
                        f"that matches this description.",
            source=SOURCE_SLIDE, slide_support=d.line, added_context=added,
            options=options,
            why_wrong={o.term: f"Your notes define {o.term} differently: “{o.meaning}”." for o in picked},
        ))

    # What is X?
    prompt = (f"In {p.slide.topic}, what is {d.term}?" if technical
              else f"In the context of {ctx}, what is meant by “{d.term}”?")
    out.append(StudyItem(
        image_id, "definition", d.term, prompt=prompt, answer=_cap(d.meaning),
        explanation=f"Your {ctx} notes define {d.term} as “{d.meaning}”. That is the key idea to "
                    f"recall whenever {d.term} comes up.",
        source=SOURCE_SLIDE, slide_support=d.line, added_context=added,
    ))
    return out


def acronym_candidates(p: ParsedSlide, a: Acronym) -> List[StudyItem]:
    bank = _concept_for_term(a.acronym)
    return [StudyItem(
        p.slide.image_id, "acronym", a.acronym,
        prompt=f"What does the acronym {a.acronym} stand for?",
        answer=a.expansion,
        explanation=f"{a.acronym} stands for {a.expansion}, as spelled out in your {p.context} notes. "
                    f"Knowing the full name helps you remember what {a.acronym} does.",
        source=SOURCE_SLIDE, slide_support=a.line,
        added_context=f"{SOURCE_LABEL}: {bank.explanation}" if bank else "",
    )]


def statement_candidates(p: ParsedSlide, term: str, line: str) -> List[StudyItem]:
    sentence = BLANK + line[len(term):]
    bank = _concept_for_term(term)
    return [StudyItem(
        p.slide.image_id, "cloze", term,
        prompt=f"Fill in the blank: {sentence}",
        answer=term,
        explanation=f"The complete statement in your {p.context} notes is “{line}”. The blank is "
                    f"{term}, the thing this statement describes.",
        source=SOURCE_SLIDE, slide_support=line,
        added_context=f"{SOURCE_LABEL}: {bank.explanation}" if bank else "",
    )]


def concept_candidates(p: ParsedSlide, m: Mention) -> List[StudyItem]:
    concept = m.concept
    options = _shuffle([concept.answer] + [name for name, _ in concept.confusers], concept.key)
    return [StudyItem(
        p.slide.image_id, "concept_mc", concept.term,
        prompt=concept.question,
        answer=concept.answer,
        explanation=concept.explanation,
        source=SOURCE_CONTEXT,
        slide_support=m.line,
        added_context=(f"{SOURCE_LABEL}. Your slide mentions “{m.alias}”; this question and its "
                       f"explanation come from general A+ Core 2 material, not from the slide."),
        options=options,
        why_wrong=dict(concept.confusers),
        mentions=[m.alias],
    )]


# --------------------------------------------------------------------------
# Step 3: validate, regenerate on rejection, skip when there isn't enough
# --------------------------------------------------------------------------


class OfflineGenerator(Generator):
    name = "offline-concepts"
    version = 2

    def generate_topic(self, slides: Sequence[SlideText], only_ids: Optional[set] = None) -> GenerationResult:
        result = GenerationResult()
        parsed = [parse_slide(s) for s in slides]
        topic_defs = [d for p in parsed for d in p.definitions]

        # Each concept-bank concept is asked once per topic, on the slide where it is most central
        home: Dict[str, Tuple[Tuple[int, int], int]] = {}
        for order, p in enumerate(parsed):
            for m in p.mentions:
                rank = (0 if m.in_title else 1, order)
                if m.concept.key not in home or rank < home[m.concept.key][0]:
                    home[m.concept.key] = (rank, p.slide.image_id)

        per_concept: Dict[str, int] = {}
        for p in parsed:
            if only_ids is not None and p.slide.image_id not in only_ids:
                continue
            groups: List[List[StudyItem]] = []
            # concept-bank questions first: they test understanding and explain the alternatives
            groups += [concept_candidates(p, m) for m in p.mentions
                       if home[m.concept.key][1] == p.slide.image_id]
            groups += [definition_candidates(p, d, topic_defs) for d in p.definitions]
            groups += [acronym_candidates(p, a) for a in p.acronyms]
            groups += [statement_candidates(p, t, ln) for t, ln in p.statements]

            accepted: List[StudyItem] = []
            # Round-robin: first one good question per concept, then a second kind if there's room.
            cursors = [0] * len(groups)
            for _round in range(MAX_ITEMS_PER_CONCEPT):
                for gi, group in enumerate(groups):
                    while cursors[gi] < len(group) and len(accepted) < MAX_ITEMS_PER_SLIDE:
                        candidate = group[cursors[gi]]
                        cursors[gi] += 1
                        key = norm(candidate.concept)
                        if per_concept.get(key, 0) >= MAX_ITEMS_PER_CONCEPT:
                            cursors[gi] = len(group)
                            break
                        if any(norm(a.concept) == key and a.kind == candidate.kind
                               for a in result.items + accepted):
                            continue  # already asked this way
                        problems = validate_item(candidate, p.text)
                        if problems:
                            result.rejected.append(Rejected(candidate, problems))
                            continue  # regenerate: try the next candidate for this concept
                        accepted.append(candidate)
                        per_concept[key] = per_concept.get(key, 0) + 1
                        break
            if not accepted:
                result.skipped_slides.append(p.slide.rel_path)
            result.items.extend(accepted)
        return result
